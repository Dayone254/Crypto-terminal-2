"""Bybit Options adapter — fetches the full BTC/ETH options board from Bybit.

Bybit v5 symbol format: BTC-27SEP24-65000-C-USDT  (5 parts, USDT suffix)
                   or:  BTC-27SEP24-65000-C         (4 parts, legacy)

Fields used:
  openInterest   — contracts outstanding
  markIv         — mark implied volatility (decimal, e.g. 0.65 = 65%)
  bid1Price, ask1Price, markPrice
  volume24h, turnover24h
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger("tpt.adapters.bybit_options")

BYBIT_API_URL = "https://api.bybit.com/v5/market/tickers"


async def aggregate_bybit_options(underlying: str = "BTC") -> list[dict[str, Any]]:
    url     = BYBIT_API_URL
    params  = {"category": "option", "baseCoin": underlying.upper()}
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(url, params=params, headers=headers)

        if response.status_code != 200:
            logger.warning("Bybit Options API returned HTTP %d", response.status_code)
            return []

        payload     = response.json()
        ret_code    = payload.get("retCode", -1)
        if ret_code != 0:
            logger.warning("Bybit API retCode=%s msg=%s", ret_code, payload.get("retMsg"))
            return []

        list_items = payload.get("result", {}).get("list", [])

        board: list[dict[str, Any]] = []
        for item in list_items:
            symbol = item.get("symbol", "")
            parts  = symbol.split("-")

            # Handle both BTC-DDMMMYY-STRIKE-TYPE and BTC-DDMMMYY-STRIKE-TYPE-USDT
            if len(parts) == 5 and parts[4].upper() in ("USDT", "USDC", "USD"):
                parts = parts[:4]   # drop the quote suffix
            if len(parts) != 4:
                continue

            expiry_str = parts[1]   # e.g. 27SEP24
            try:
                strike = float(parts[2])
            except ValueError:
                continue

            opt_type = parts[3].upper()
            if opt_type not in ("C", "P"):
                continue

            # Open Interest in contract units (1 contract = 1 underlying coin).
            # OI USD = contracts × underlying spot price (not strike).
            # Bybit tickers expose 'underlyingPrice' for the live spot, use it when present.
            open_interest_contracts = float(item.get("openInterest", 0) or 0)
            mark_price              = float(item.get("markPrice",     0) or 0)
            underlying_px           = float(item.get("underlyingPrice", 0) or 0)
            # Fallback hierarchy: underlyingPrice → markPrice / option_delta_proxy → strike
            spot_proxy = underlying_px if underlying_px > 0 else strike

            if open_interest_contracts > 0:
                open_interest_usd = open_interest_contracts * spot_proxy
            else:
                turnover = float(item.get("turnover24h", 0) or 0)
                if turnover <= 0:
                    continue
                open_interest_usd = turnover   # use turnover as proxy for illiquid strikes

            # IV — markIv is a decimal (e.g. 0.65) on Bybit
            mark_iv = float(item.get("markIv", 0.50) or 0.50)
            if mark_iv > 5.0:          # sanity: if > 500% it must be in pct form
                mark_iv = mark_iv / 100.0
            if mark_iv <= 0:
                mark_iv = 0.50

            board.append({
                "venue":              "Bybit",
                "symbol":             symbol,
                "underlying":         underlying,
                "expiry_str":         expiry_str,
                "strike":             strike,
                "type":               opt_type,
                "bid_price":          float(item.get("bid1Price",  0) or 0),
                "ask_price":          float(item.get("ask1Price",  0) or 0),
                "open_interest":      open_interest_contracts,
                "open_interest_usd":  open_interest_usd,
                "volume":             float(item.get("volume24h",  0) or 0),
                "mark_price":         mark_price,
                "underlying_price":   spot_proxy,
                "implied_volatility": mark_iv,
            })

        logger.info("Bybit options: %d contracts parsed for %s", len(board), underlying)
        return board

    except Exception as exc:
        logger.warning("Exception fetching Bybit options: %s", exc)
        return []
