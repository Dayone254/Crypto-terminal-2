"""Binance Futures adapter for Funding Rate and Open Interest metrics."""
from __future__ import annotations

from typing import Any

import httpx

BINANCE_FUTURES_API = "https://fapi.binance.com"

# Shared singleton client
_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(base_url=BINANCE_FUTURES_API, timeout=5.0)
    return _client



async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def get_premium_index(symbol: str) -> dict[str, float] | None:
    """Fetch live funding rate for a specific USDT pair.

    Args:
        symbol: e.g. "BTCUSDT"
    
    Returns:
        {"funding_rate": float} e.g. {"funding_rate": -0.0001}
    """
    client = get_client()
    try:
        res = await client.get("/fapi/v1/premiumIndex", params={"symbol": symbol})
        if res.status_code == 200:
            data = res.json()
            return {
                "funding_rate": float(data.get("lastFundingRate") or 0.0)
            }
        return None
    except Exception:
        return None


async def get_open_interest_hist(symbol: str) -> dict[str, float] | None:
    """Fetch Open Interest history (1d period) to compute delta.

    Args:
        symbol: e.g. "BTCUSDT"
    
    Returns:
        {"oi_change_pct": float}
    """
    client = get_client()
    try:
        res = await client.get("/futures/data/openInterestHist", params={"symbol": symbol, "period": "1d", "limit": 2})
        if res.status_code == 200:
            data = res.json()
            if len(data) == 2:
                old_oi_value = float(data[0].get("sumOpenInterestValue") or 0.0)
                new_oi_value = float(data[1].get("sumOpenInterestValue") or 0.0)
                if old_oi_value > 0:
                    delta = ((new_oi_value - old_oi_value) / old_oi_value) * 100.0
                    return {"oi_change_pct": delta}
        return {"oi_change_pct": 0.0}
    except Exception:
        return {"oi_change_pct": 0.0}


async def get_futures_klines(symbol: str, interval: str = "1h", limit: int = 300, before_ts: int | None = None) -> list[list[Any]]:
    """Fetch live Kline candlestick data from Binance Futures API.

    Args:
        symbol: e.g. "BTCUSDT" or "NEARUSDT"
        interval: e.g. "15m", "1h", "6h", "1d"
        limit: number of candles (default 300)
        before_ts: Unix timestamp (seconds) to fetch candles before

    Returns:
        Formatted candle lists: [[timestamp_sec, low, high, open, close, volume], ...]
    """
    client = get_client()
    try:
        formatted_sym = symbol.upper().replace("-USD", "").replace("-", "")
        if not formatted_sym.endswith("USDT") and not formatted_sym.endswith("BUSD"):
            formatted_sym = f"{formatted_sym}USDT"

        params: dict[str, Any] = {
            "symbol": formatted_sym,
            "interval": interval,
            "limit": limit
        }
        if before_ts:
            params["endTime"] = int(before_ts) * 1000

        res = await client.get(
            "/fapi/v1/klines",
            params=params
        )
        if res.status_code == 200:
            klines = res.json()
            # Binance Kline format: [open_time, open, high, low, close, volume, ...]
            # Format to TapeRadar standard: [time_sec, low, high, open, close, volume]
            results = []
            for k in klines:
                t_sec = int(k[0]) // 1000
                open_p = float(k[1])
                high_p = float(k[2])
                low_p = float(k[3])
                close_p = float(k[4])
                vol = float(k[5])
                results.append([t_sec, open_p, high_p, low_p, close_p, vol])

            return results
        return []
    except Exception:
        return []
