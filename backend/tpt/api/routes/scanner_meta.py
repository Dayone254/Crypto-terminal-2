"""Scanner enrichment routes: 1h deltas, CVD, sparklines, universe count.

All values are computed from real Binance futures data — no synthetic fills.
When upstream data is unavailable for a symbol the fields are None and the
frontend renders an honest empty state instead of a fabricated number.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import APIRouter

from tpt.adapters.binance_futures import get_futures_klines

router = APIRouter()

# ── RAM caches ────────────────────────────────────────────────────────────────
# The dashboard polls every 5s; upstream Binance calls are batched and cached
# so the scanner stays cheap for both sides.
_ENRICH_CACHE: dict[str, dict[str, Any]] = {}
_ENRICH_CACHE_TS: dict[str, float] = {}
_ENRICH_TTL: float = 60.0  # seconds

_UNIVERSE_CACHE: int | None = None
_UNIVERSE_CACHE_TS: float = 0.0
_UNIVERSE_TTL: float = 300.0  # exchangeInfo is slow-moving; 5 min is plenty
_UNIVERSE_FAIL_TS: float = 0.0  # negative-cache: back off after a failed fetch
_UNIVERSE_FAIL_TTL: float = 60.0

_MAX_CONCURRENCY = 8


def _to_usdt(product_id: str) -> str:
    """'BNB-USD' → 'BNBUSDT' (mirrors the klines adapter convention)."""
    sym = product_id.upper().replace("-USD", "").replace("-", "")
    return sym if sym.endswith("USDT") else f"{sym}USDT"


def _closes_from_klines(klines: list[list[Any]]) -> list[float]:
    """Adapter format [ts, open, high, low, close, volume] → close series."""
    closes: list[float] = []
    for k in klines:
        try:
            c = float(k[4])
            if c > 0:
                closes.append(c)
        except (TypeError, ValueError, IndexError):
            continue
    return closes


def _cvd_from_klines(klines: list[list[Any]]) -> float | None:
    """Cumulative volume delta over the window: Σ(close−open > 0 ? vol : −vol).

    Sign convention: positive = net taker buying pressure. Returns None when
    the window carries no usable volume at all.
    """
    cvd = 0.0
    saw_volume = False
    for k in klines:
        try:
            o = float(k[1])
            c = float(k[4])
            v = float(k[5])
        except (TypeError, ValueError, IndexError):
            continue
        if v <= 0:
            continue
        saw_volume = True
        cvd += v if c >= o else -v
    return cvd if saw_volume else None


async def _enrich_symbol(product_id: str) -> dict[str, Any]:
    """Real 1h delta, 24h CVD and a 24×1h close sparkline for one symbol."""
    now = time.time()
    cached = _ENRICH_CACHE.get(product_id)
    if cached and now - _ENRICH_CACHE_TS.get(product_id, 0.0) < _ENRICH_TTL:
        return cached

    empty: dict[str, Any] = {"change_1h_pct": None, "cvd_24h_usd": None, "sparkline": None}
    try:
        klines = await get_futures_klines(_to_usdt(product_id), interval="1h", limit=25)
        # 25 bars → 24 complete deltas; drop the last (still-forming) bar.
        complete = klines[:-1] if len(klines) >= 2 else []
        closes = _closes_from_klines(complete)

        change_1h: float | None = None
        if len(closes) >= 2:
            first, last = closes[0], closes[-1]
            if first > 0:
                change_1h = round((last - first) / first * 100.0, 2)

        sparkline: list[float] | None = None
        if closes:
            sparkline = [round(c, 8) for c in closes]

        cvd = _cvd_from_klines(complete)

        payload = {
            "change_1h_pct": change_1h,
            "cvd_24h_usd": round(cvd, 0) if cvd is not None else None,
            "sparkline": sparkline,
        }
        _ENRICH_CACHE[product_id] = payload
        _ENRICH_CACHE_TS[product_id] = now
        return payload
    except Exception:
        # Honest empty state — never a synthetic number.
        return empty


@router.get("/scanner/enrichment")
async def get_scanner_enrichment(product_ids: str) -> dict[str, dict[str, Any]]:
    """Batch enrichment: ?product_ids=BTC-USD,ETH-USD,SOL-USD (max 60).

    Returns a map keyed by product_id; symbols that fail upstream simply carry
    None fields so the frontend can show an honest dash.
    """
    raw = [p.strip().upper() for p in (product_ids or "").split(",") if p.strip()]
    pids = raw[:60]
    if not pids:
        return {}

    sem = asyncio.Semaphore(_MAX_CONCURRENCY)

    async def _bounded(pid: str) -> tuple[str, dict[str, Any]]:
        async with sem:
            return pid, await _enrich_symbol(pid)

    results = await asyncio.gather(*(_bounded(pid) for pid in pids))
    return dict(results)


@router.get("/scanner/universe-count")
async def get_universe_count() -> dict[str, Any]:
    """Number of USDT-margined perpetual futures trading on Binance."""
    global _UNIVERSE_CACHE, _UNIVERSE_CACHE_TS, _UNIVERSE_FAIL_TS
    now = time.time()
    if _UNIVERSE_CACHE is not None and now - _UNIVERSE_CACHE_TS < _UNIVERSE_TTL:
        return {"universe_count": _UNIVERSE_CACHE}
    if now - _UNIVERSE_FAIL_TS < _UNIVERSE_FAIL_TTL:
        return {"universe_count": None}

    try:
        from tpt.adapters.binance_futures import get_client

        client = get_client()
        # exchangeInfo is a multi-MB payload; the shared client's 5s default
        # times out on a slow link, so this call overrides the timeout.
        res = await client.get("/fapi/v1/exchangeInfo", timeout=20.0)
        if res.status_code == 200:
            info = res.json()
            count = sum(
                1
                for s in info.get("symbols", [])
                if s.get("contractType") == "PERPETUAL"
                and s.get("quoteAsset") == "USDT"
                and s.get("status") == "TRADING"
            )
            _UNIVERSE_CACHE = count
            _UNIVERSE_CACHE_TS = now
            return {"universe_count": count}
    except Exception:
        pass
    _UNIVERSE_FAIL_TS = time.time()
    return {"universe_count": None}
