"""OKX Options adapter — fetches the full BTC/ETH options board from OKX.

Strategy:
  1. Fetch all option tickers via /api/v5/market/tickers?instType=OPTION&uly={under}-USD
  2. Fetch Open Interest per instrument via /api/v5/public/open-interest?instType=OPTION&uly={under}-USD
  3. Merge on instId — tickers supply bid/ask/IV; OI endpoint supplies open_interest in coin units.

OKX instId formats handled:
  Legacy : BTC-USD-240927-65000-C   (5 dash-parts)
  Current: BTC-USD_UM-260921-73000-C (parts[0]=BTC, parts[1]=USD_UM, parts[2]=YYMMDD, parts[3]=K, parts[4]=type)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger("tpt.adapters.okx_options")

OKX_BASE = "https://www.okx.com/api/v5"
MONTHS   = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"]


def _parse_okx_inst_id(inst_id: str) -> tuple[str, float, str] | None:
    """
    Returns (expiry_str, strike, opt_type) or None if unparseable.

    Handles both:
      BTC-USD-240927-65000-C       → parts after first split: [BTC, USD, 240927, 65000, C]
      BTC-USD_UM-260921-73000-C    → after replacing underscore join: same 5 meaningful parts
    """
    # Normalise: treat USD_UM, USD_DM etc as just "USD" so we always get 5 real parts
    normalised = inst_id.replace("USD_UM", "USD").replace("USD_DM", "USD")
    parts = normalised.split("-")

    # Expect: [UNDERLYING, QUOTE, YYMMDD, STRIKE, TYPE]
    if len(parts) < 5:
        return None

    # YYMMDD is parts[2], strike parts[3], type parts[4]
    expiry_raw = parts[2]
    strike_str = parts[3]
    opt_type   = parts[4].upper()

    if opt_type not in ("C", "P"):
        return None

    try:
        strike = float(strike_str)
    except ValueError:
        return None

    try:
        yy = expiry_raw[:2]
        mm = int(expiry_raw[2:4])
        dd = expiry_raw[4:6]
        month_str = MONTHS[mm - 1] if 1 <= mm <= 12 else "JAN"
        expiry_str = f"{dd}{month_str}{yy}"
    except (ValueError, IndexError):
        return None

    return expiry_str, strike, opt_type


async def aggregate_okx_options(underlying: str = "BTC") -> list[dict[str, Any]]:
    uly = f"{underlying.upper()}-USD"

    ticker_resp = None
    oi_resp = None

    async with httpx.AsyncClient(timeout=2.0) as client:

        # Fire both requests concurrently manually
        try:
            ticker_task = asyncio.create_task(client.get(f"{OKX_BASE}/market/tickers", params={"instType": "OPTION", "uly": uly}))
            oi_task     = asyncio.create_task(client.get(f"{OKX_BASE}/public/open-interest", params={"instType": "OPTION", "uly": uly}))

            ticker_resp, oi_resp = await asyncio.gather(ticker_task, oi_task)
        except Exception as exc:
            logger.warning("OKX concurrent fetch error: %s", exc)

    # ── Parse Open Interest map: instId → (oi_coin, oi_usd) ────────────────
    oi_map_coin: dict[str, float] = {}
    oi_map_usd: dict[str, float] = {}
    if oi_resp is not None and oi_resp.status_code == 200:
        for row in oi_resp.json().get("data", []):
            inst_id = row.get("instId", "")
            oi_usd  = float(row.get("oiUsd", 0) or 0)
            oi_coin = float(row.get("oi",    0) or 0)
            if oi_coin > 0:
                oi_map_coin[inst_id] = oi_coin
            if oi_usd > 0:
                oi_map_usd[inst_id] = oi_usd

    # ── Parse tickers ────────────────────────────────────────────────────────
    if ticker_resp is None or ticker_resp.status_code != 200:
        logger.warning("OKX tickers fetch failed")
        return []

    board: list[dict[str, Any]] = []
    for item in ticker_resp.json().get("data", []):
        inst_id = item.get("instId", "")
        parsed  = _parse_okx_inst_id(inst_id)
        if not parsed:
            continue

        expiry_str, strike, opt_type = parsed

        oi_coin = oi_map_coin.get(inst_id, 0.0)
        oi_usd  = oi_map_usd.get(inst_id, 0.0)
        if oi_coin <= 0 or oi_usd <= 0:
            norm_key = inst_id.replace("USD_UM", "USD").replace("USD_DM", "USD")
            if oi_coin <= 0: oi_coin = oi_map_coin.get(norm_key, 0.0)
            if oi_usd <= 0:  oi_usd  = oi_map_usd.get(norm_key, 0.0)

        # Compute synthetic spot from the ratio when both are available from OI endpoint
        if oi_coin > 0 and oi_usd > 0:
            _synthetic_spot = oi_usd / oi_coin   # implied USD/contract price ≈ spot
        else:
            _synthetic_spot = strike              # last resort fallback

        # Fill missing side using spot (not strike) to avoid biasing contract counts
        if oi_usd <= 0 and oi_coin > 0:
            oi_usd = oi_coin * _synthetic_spot
        if oi_coin <= 0 and oi_usd > 0:
            # Derive contracts from USD notional using synthetic spot, not strike
            oi_coin = oi_usd / _synthetic_spot

        if oi_usd <= 0:
            continue  # skip illiquid strikes

        bid_px  = float(item.get("bidPx", 0) or 0)
        ask_px  = float(item.get("askPx", 0) or 0)
        last_px = float(item.get("last",  0) or 0)

        # OKX tickers do not expose markIv in the bulk ticker endpoint.
        # Derive best-effort IV from the mark IV field when available, otherwise
        # use a conservative crypto default scaled by moneyness.
        raw_iv = float(item.get("markIv", 0) or 0)
        if raw_iv > 0:
            iv = raw_iv / 100.0 if raw_iv > 5.0 else raw_iv   # handle both pct and decimal
        else:
            # Fallback: use a moneyness-based vol estimate.
            # ATM ≈ 0.65, deep OTM adds a vol premium.
            if oi_coin > 0 and oi_usd > 0:
                synthetic_spot = oi_usd / oi_coin
                moneyness = abs(strike - synthetic_spot) / synthetic_spot if synthetic_spot > 0 else 0.0
            else:
                moneyness = 0.0
            iv = min(0.65 + moneyness * 0.5, 2.5)   # cap at 250% to avoid garbage

        board.append({
            "venue":              "OKX",
            "symbol":             inst_id,
            "underlying":         underlying,
            "expiry_str":         expiry_str,
            "strike":             strike,
            "type":               opt_type,
            "bid_price":          bid_px,
            "ask_price":          ask_px,
            "open_interest":      oi_coin,
            "open_interest_usd":  oi_usd,
            "volume":             float(item.get("vol24h",    0) or 0),
            "mark_price":         last_px,
            "implied_volatility": iv,
        })

    logger.info("OKX options: %d contracts parsed for %s", len(board), underlying)
    return board
