"""Markets API routes — fetch latest symbol setup quality, features, and limit ladders."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, status

from tpt.db.connection import AsyncSessionLocal
from tpt.db.queries import get_latest_ladder_and_score
from tpt.engine.belief import coverage_band
from tpt.engine.ladder import format_ladder_text, sanitize_ladder_dict

router = APIRouter()


import time

_MARKETS_CACHE: list[dict[str, Any]] = []
_MARKETS_CACHE_TS: float = 0.0
_MARKETS_CACHE_TTL: float = 15.0  # 15 seconds RAM cache

# Per-symbol detail cache — avoids cold DB reads on every 5s poll from the asset page.
_DETAIL_CACHE: dict[str, dict[str, Any]] = {}
_DETAIL_CACHE_TS: dict[str, float] = {}
_DETAIL_CACHE_TTL: float = 30.0  # 30 seconds

@router.get("/markets", response_model=list[dict[str, Any]])
async def list_markets() -> list[dict[str, Any]]:
    """Return all candidates from the most recent scan run that produced data."""
    global _MARKETS_CACHE, _MARKETS_CACHE_TS
    now = time.time()
    if _MARKETS_CACHE and (now - _MARKETS_CACHE_TS < _MARKETS_CACHE_TTL):
        return _MARKETS_CACHE

    from sqlalchemy import select
    from tpt.db.models import Feature, Ladder, ScanRun, Score, Symbol

    async with AsyncSessionLocal() as db:
        # Step 1: Get latest completed ScanRun ID (status == DONE)
        recent_res = await db.execute(
            select(ScanRun.id)
            .where(ScanRun.status == "DONE")
            .order_by(ScanRun.started_at.desc())
            .limit(1)
        )
        latest_id = recent_res.scalar_one_or_none()

        if not latest_id:
            # Fallback to any scan_run_id present in scores table
            recent_res = await db.execute(
                select(Score.scan_run_id)
                .order_by(Score.computed_at.desc())
                .limit(1)
            )
            latest_id = recent_res.scalar_one_or_none()
            if not latest_id:
                return []

        # Step 2: Load scores for this run — uses idx_scores_composite index
        scores_res = await db.execute(
            select(Score)
            .where(Score.scan_run_id == latest_id)
            .order_by(Score.composite_score.desc())
        )
        score_rows = scores_res.scalars().all()
        if not score_rows:
            return []

        pids = [s.product_id for s in score_rows]

        # Step 3: Bulk-load features, ladders, symbols for these product_ids — one query each
        feat_res = await db.execute(
            select(Feature).where(Feature.scan_run_id == latest_id)
        )
        feat_map: dict[str, Feature] = {f.product_id: f for f in feat_res.scalars().all()}

        lad_res = await db.execute(
            select(Ladder).where(Ladder.scan_run_id == latest_id)
        )
        lad_map: dict[str, Ladder] = {l.product_id: l for l in lad_res.scalars().all()}

        sym_res = await db.execute(
            select(Symbol).where(Symbol.product_id.in_(pids))
        )
        sym_map: dict[str, Symbol] = {s.product_id: s for s in sym_res.scalars().all()}

        # Step 4: Build response
        results = []
        for score_rec in score_rows:
            feat_rec = feat_map.get(score_rec.product_id)
            lad_rec = lad_map.get(score_rec.product_id)
            sym_rec = sym_map.get(score_rec.product_id)

            ladder_dict = None
            if lad_rec:
                ladder_dict = sanitize_ladder_dict({
                    "tranche_a_price":    lad_rec.tranche_a_price,
                    "tranche_b_price":    lad_rec.tranche_b_price,
                    "stop_price":         lad_rec.stop_price,
                    "target_1_price":     lad_rec.target_1_price,
                    "target_2_price":     lad_rec.target_2_price,
                    "tranche_a_size_pct": lad_rec.tranche_a_size_pct,
                    "tranche_b_size_pct": lad_rec.tranche_b_size_pct,
                    "trade_direction":    score_rec.trade_direction,
                    "target_r":           getattr(lad_rec, "target_r", None),
                })

            score_breakdown = json.loads(score_rec.score_breakdown) if score_rec.score_breakdown else {}
            tags = score_breakdown.get("tags", [])

            results.append({
                "product_id": score_rec.product_id,
                "last_price": feat_rec.last_price if feat_rec else None,
                "day_change_pct": feat_rec.day_change_pct if feat_rec else None,
                "composite_score": score_rec.composite_score,
                "edge": score_rec.edge,
                "coverage": score_rec.coverage,
                "coverage_band": coverage_band(score_rec.coverage) if score_rec.coverage is not None else None,
                "trade_direction": getattr(score_rec, "trade_direction", "LONG"),
                "label": score_rec.label,
                "pos_in_range": feat_rec.pos_in_range if feat_rec else None,
                "quote_vol_24h": feat_rec.quote_vol_24h if feat_rec else None,
                "ladder": ladder_dict,
                "tags": tags,
                "pinned": bool(sym_rec and sym_rec.on_watchlist),
            })

        _MARKETS_CACHE = results
        _MARKETS_CACHE_TS = time.time()
        return results





async def _fetch_and_cache_options(underlying: str, spot: float):
    """Asynchronously fetch options board and store in ws_memory cache without blocking API response."""
    try:
        from tpt.engine.options_flow import calculate_macro_gamma_exposure
        from tpt.engine.ws_memory import ws_memory
        gamma_data = await calculate_macro_gamma_exposure(underlying, spot)
        if gamma_data:
            ws_memory.macro_options_cache[underlying] = gamma_data
    except Exception:
        pass


import httpx

_BTC_PAIRS_CACHE: dict[str, dict[str, float]] = {}
_BTC_PAIRS_CACHE_TS: float = 0.0
_BTC_PAIRS_CACHE_TTL: float = 300.0  # 5 mins
_btc_pairs_task = None

async def _fetch_btc_pair_perf(candidates: list[dict[str, Any]]) -> None:
    """Background task to fetch 7D and 30D performance for Alt/BTC pairs from Binance Spot API."""
    global _BTC_PAIRS_CACHE, _BTC_PAIRS_CACHE_TS
    try:
        symbols_to_fetch = []
        for c in candidates:
            base = c.get("product_id", "").split("-")[0].upper()
            if base != "BTC":
                symbols_to_fetch.append(f"{base}BTC")
                
        if not symbols_to_fetch:
            return

        async with httpx.AsyncClient() as client:
            # 1. Fetch valid exchange symbols first to prevent 400 Bad Request on invalid symbols!
            x_info = await client.get('https://api.binance.com/api/v3/exchangeInfo')
            valid_symbols = set()
            if x_info.status_code == 200:
                valid_symbols = {s["symbol"] for s in x_info.json().get("symbols", []) if s.get("status") == "TRADING"}
                
            safe_symbols = [s for s in symbols_to_fetch if s in valid_symbols]
            
            if not safe_symbols:
                return

            symbols_json = json.dumps(safe_symbols[:100]) # cap at 100

            # 2. Fetch 7D and 30D ticker data for safe symbols
            r_7d = await client.get('https://api.binance.com/api/v3/ticker', params={"windowSize": "7d", "symbols": symbols_json})
            r_30d = await client.get('https://api.binance.com/api/v3/ticker', params={"windowSize": "30d", "symbols": symbols_json})
            
            if r_7d.status_code == 200 and r_30d.status_code == 200:
                data_7d = {x["symbol"]: float(x["priceChangePercent"]) for x in r_7d.json()}
                data_30d = {x["symbol"]: float(x["priceChangePercent"]) for x in r_30d.json()}
                
                # Combine them
                res = {}
                for sym, v7 in data_7d.items():
                    if sym.endswith("BTC"):
                        asset = sym.replace("BTC", "")
                        res[asset] = {
                            "7d_pct": v7,
                            "30d_pct": data_30d.get(sym, v7)  # Fallback to 7d if 30d missing
                        }
                _BTC_PAIRS_CACHE = res
                _BTC_PAIRS_CACHE_TS = time.time()
            else:
                print(f"Warning: Failed to fetch BTC pairs from Binance. 7D Status: {r_7d.status_code}, 30D Status: {r_30d.status_code}")
    except Exception as e:
        print(f"Error fetching BTC pairs: {e}")



_RS_MATRIX_CACHE: dict[str, Any] = {}
_RS_MATRIX_CACHE_TS: float = 0.0
_RS_MATRIX_CACHE_TTL: float = 60.0  # 60 seconds RAM cache for RS matrix


@router.get("/markets/rs-matrix", response_model=dict[str, Any])
async def get_rs_matrix() -> dict[str, Any]:
    """Return real-time BTC Gamma Regime state and Relative Strength matrix rankings across all candidates."""
    global _RS_MATRIX_CACHE, _RS_MATRIX_CACHE_TS, _btc_pairs_task, _BTC_PAIRS_CACHE_TS
    now = time.time()
    
    if _RS_MATRIX_CACHE and (now - _RS_MATRIX_CACHE_TS < _RS_MATRIX_CACHE_TTL):
        return _RS_MATRIX_CACHE

    from tpt.engine.relative_strength import calculate_btc_regime, compute_relative_strength_matrix
    from tpt.engine.ws_memory import ws_memory

    # 1. Fetch current candidates list
    candidates = await list_markets()
    
    # Trigger background cache fetch for BTC pairs if stale or empty
    if now - _BTC_PAIRS_CACHE_TS > _BTC_PAIRS_CACHE_TTL:
        if _btc_pairs_task is None or _btc_pairs_task.done():
            _btc_pairs_task = asyncio.create_task(_fetch_btc_pair_perf(candidates))

    # 2. Extract BTC spot price and cached BTC gamma metrics
    btc_spot = 0.0
    for c in candidates:
        if "BTC" in c.get("product_id", "").upper():
            btc_spot = float(c.get("last_price", 0.0) or 0.0)
            break

    btc_gamma = ws_memory.get_macro_options("BTC") or {}
    btc_regime_info = calculate_btc_regime(btc_spot, btc_gamma)

    # 3. Compute Altcoin RS Z-score Matrix
    ranked_matrix = compute_relative_strength_matrix(candidates, btc_regime_info, _BTC_PAIRS_CACHE)


    # 4. Summary counters
    long_leaders = [c for c in ranked_matrix if c.get("rs_signal") in ("LONG_LEADER", "OUTPERFORMER")]
    short_laggards = [c for c in ranked_matrix if c.get("rs_signal") in ("SHORT_LAGGARD", "DIVERGENT_SHORT", "UNDERPERFORMER")]

    res = {
        "btc_regime": btc_regime_info,
        "summary": {
            "total_universe": len(ranked_matrix),
            "long_leaders_count": len(long_leaders),
            "short_laggards_count": len(short_laggards),
        },
        "candidates": ranked_matrix,
    }
    _RS_MATRIX_CACHE = res
    _RS_MATRIX_CACHE_TS = now
    return res


@router.get("/markets/{product_id}", response_model=dict[str, Any])
@router.get("/markets/{product_id}/ladder", response_model=dict[str, Any])
async def get_market_detail(product_id: str, expiry: str = "ALL") -> dict[str, Any]:
    """Return latest setup quality, score, label, ladder, and options flow for a given symbol."""
    pid_upper = product_id.upper()
    now = time.time()

    # Serve from RAM cache if fresh (avoids cold DB read on every 5-20s poll).
    cached = _DETAIL_CACHE.get(pid_upper)
    if cached and (now - _DETAIL_CACHE_TS.get(pid_upper, 0.0)) < _DETAIL_CACHE_TTL:
        return cached

    async with AsyncSessionLocal() as db:
        data: dict[str, Any] = await get_latest_ladder_and_score(db, pid_upper) or {}
        if not data:
            data = {"product_id": pid_upper, "symbol": pid_upper, "last_price": 0.0}

        from tpt.engine.ws_memory import ws_memory
        underlying = pid_upper.split("-")[0]

        cached_options = ws_memory.get_macro_options(underlying)
        if cached_options and isinstance(cached_options, dict) and cached_options.get("underlying", "").upper() == underlying:
            data["options_flow"] = cached_options
        else:
            # Do NOT block the HTTP response — return None immediately.
            # Frontend receives live GEX via WebSocket (/api/v1/ws/options/{symbol}).
            data["options_flow"] = None

        _DETAIL_CACHE[pid_upper] = data
        _DETAIL_CACHE_TS[pid_upper] = now
        return data



@router.get("/options/flow", response_model=dict[str, Any])
@router.get("/options/flow/{product_id}", response_model=dict[str, Any])
async def get_options_flow(product_id: str = "BTC-USD", underlying: str | None = None, expiry: str = "ALL") -> dict[str, Any]:
    """Return live macro options flow & GEX levels for a given symbol or underlying."""
    from tpt.engine.ws_memory import ws_memory
    from tpt.engine.options_flow import calculate_macro_gamma_exposure
    symbol_coin = (underlying or product_id.split("-")[0]).upper()

    cached = ws_memory.get_macro_options(symbol_coin)
    # Only serve cached data for ALL filter — specific expiry filters must always recompute
    if cached and isinstance(cached, dict) and expiry.upper() == "ALL":
        return cached

    res = await calculate_macro_gamma_exposure(symbol_coin, 0.0, expiry_filter=expiry)
    if res and expiry.upper() == "ALL":
        ws_memory.macro_options_cache[symbol_coin] = res
    return res or {}


@router.get("/markets/{product_id}/candles", response_model=list[list[Any]])
async def get_market_candles(
    product_id: str,
    granularity: int = 3600,
    limit: int = 1000,
    before_ts: int | None = None,
) -> list[list[Any]]:
    """Return OHLCV candles for a symbol.

    Strategy (newest coins first, then fill backward):
    1. Load stored historical candles from the SQLite DB for the requested
       time window (fast, no external API call).
    2. If the DB candles don't reach the present (or DB is empty), fill the
       recent gap with up to 300 live candles from Coinbase.
    3. Fall back to Binance Futures if Coinbase returns empty.

    Query params:
        granularity  — candle size in seconds (900, 3600, 21600, 86400)
        limit        — max candles to return (default 1000, max 5000)
        before_ts    — Unix timestamp (seconds); return only candles BEFORE
                       this time (used for scroll-left pagination)
    """
    import asyncio
    from datetime import UTC, datetime

    from tpt.adapters.binance_futures import get_futures_klines
    from tpt.adapters.coinbase import CoinbaseAdapter
    from tpt.backtest.storage import load_historical_candles_sync

    limit = max(1, min(limit, 5000))
    sym = product_id.upper()
    now_ts = int(datetime.now(UTC).timestamp())

    # ── 1. Live market candles (initial load without before_ts) ───────────
    tf_map = {900: "15m", 3600: "1h", 14400: "4h", 21600: "6h", 86400: "1d"}
    interval = tf_map.get(granularity, "1h")

    if not before_ts:
        try:
            live_klines = await asyncio.wait_for(
                get_futures_klines(sym, interval=interval, limit=min(limit, 1000)),
                timeout=3.0
            )
            if live_klines and len(live_klines) > 0:
                return live_klines
        except Exception:
            pass

        # Coinbase REST fallback (Coinbase valid granularities: 60, 300, 900, 3600, 21600, 86400)
        cb_granularity = 3600 if granularity == 14400 else granularity
        try:
            cb_adapter = CoinbaseAdapter()
            cb_candles = await cb_adapter.get_candles(
                product_id=sym if "-" in sym else f"{sym}-USD",
                granularity=cb_granularity,
                limit=min(limit, 300)
            )
            if cb_candles:
                formatted_cb = []
                for c in reversed(cb_candles):  # Coinbase returns newest first
                    t_sec = int(c[0])
                    low_p = float(c[1])
                    high_p = float(c[2])
                    open_p = float(c[3])
                    close_p = float(c[4])
                    vol = float(c[5])
                    formatted_cb.append([t_sec, open_p, high_p, low_p, close_p, vol])
                return formatted_cb
        except Exception:
            pass

    # ── 2. DB historical candles & fallback ────────────────────────────────
    end_ts = before_ts if before_ts else now_ts
    db_candles: list[list[Any]] = await asyncio.to_thread(
        load_historical_candles_sync,
        symbol=sym,
        granularity=granularity,
        end_ts=end_ts,
        limit=limit,
    )

    if before_ts and not db_candles:
        try:
            binance_raw = await asyncio.wait_for(
                get_futures_klines(sym, interval=interval, limit=min(limit, 1000), before_ts=before_ts),
                timeout=3.0
            )
            if binance_raw:
                return binance_raw
        except Exception:
            pass

    return db_candles or []






@router.get("/markets/{product_id}/trades/history", response_model=list[dict[str, Any]])
async def get_market_trade_history(product_id: str) -> list[dict[str, Any]]:
    """Return distinct historical scan/trade ladders for a given symbol, deduplicated by time & price."""
    from datetime import datetime

    from sqlalchemy import select

    from tpt.db.models import Ladder, Score

    async with AsyncSessionLocal() as db:
        stmt = (
            select(Score, Ladder)
            .join(Ladder, (Score.product_id == Ladder.product_id) & (Score.scan_run_id == Ladder.scan_run_id))
            .where(Score.product_id == product_id.upper())
            .order_by(Score.computed_at.asc())  # ASC so dedup pointer advances forward in time
            .limit(100)
        )
        res = await db.execute(stmt)
        rows = res.all()

        history = []
        last_added_time: datetime | None = None
        last_added_price: float | None = None

        for score_rec, lad_rec in rows:
            dt = datetime.fromisoformat(score_rec.computed_at) if isinstance(score_rec.computed_at, str) else score_rec.computed_at
            price = lad_rec.tranche_a_price

            # Deduplication: Skip if setup occurred within 4 hours AND price is within 2% of previous setup
            if last_added_time and last_added_price and price and price > 0:
                time_diff = abs((last_added_time - dt).total_seconds())
                price_diff_pct = abs((price - last_added_price) / last_added_price) * 100.0

                if time_diff < 14400 and price_diff_pct < 2.0:
                    continue  # Skip duplicate scan entry

            raw_hist = {
                "tranche_a_price": lad_rec.tranche_a_price,
                "tranche_b_price": lad_rec.tranche_b_price,
                "stop_price": lad_rec.stop_price,
                "target_1_price": lad_rec.target_1_price,
                "target_2_price": lad_rec.target_2_price,
                "target_r": getattr(lad_rec, "target_r", None),
            }
            sanitized = sanitize_ladder_dict(raw_hist) or raw_hist

            history.append({
                "computed_at": score_rec.computed_at,
                "trade_direction": getattr(score_rec, "trade_direction", "LONG"),
                "composite_score": score_rec.composite_score,
                "label": score_rec.label,
                "tranche_a_price": sanitized["tranche_a_price"],
                "tranche_b_price": sanitized["tranche_b_price"],
                "stop_price": sanitized["stop_price"],
                "target_1_price": sanitized["target_1_price"],
                "target_2_price": sanitized["target_2_price"],
            })

            last_added_time = dt
            last_added_price = price

        return history
