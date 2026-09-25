import logging
from typing import Any

import httpx

logger = logging.getLogger("tpt.adapters.binance_options")

EAPI_URL = "https://eapi.binance.com"

async def fetch_options_tickers(underlying: str = "BTC") -> list[dict[str, Any]]:
    """
    Fetches the 24hr ticker data for all active options on Binance for a specific underlying asset.
    E.g. underlying="BTC" -> BTC-240927-65000-C
    """
    url = f"{EAPI_URL}/eapi/v1/ticker"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=2.0)
            if response.status_code != 200:
                logger.error(f"Failed to fetch Binance options tickers: HTTP {response.status_code}")
                return []
            data = response.json()
            # Filter for the requested underlying asset (e.g. starts with BTC-)
            filtered = [d for d in data if d.get("symbol", "").startswith(f"{underlying}-")]
            return filtered
    except Exception as e:
        logger.error(f"Exception fetching Binance options tickers: {e}")
        return []

async def fetch_options_mark_prices(underlying: str = "BTC") -> list[dict[str, Any]]:
    """
    Fetches the Mark Price and IV for all option symbols.
    """
    url = f"{EAPI_URL}/eapi/v1/mark"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=2.0)

            if response.status_code != 200:
                return []
            data = response.json()
            filtered = [d for d in data if d.get("symbol", "").startswith(f"{underlying}-")]
            return filtered
    except Exception as e:
        logger.error(f"Exception fetching mark prices: {e}")
        return []

async def aggregate_options_board(underlying: str = "BTC") -> list[dict[str, Any]]:
    """
    Combines ticker stats (volume, open interest) with mark prices (IV) into a cohesive Option Board.
    """
    tickers = await fetch_options_tickers(underlying)
    mark_prices = await fetch_options_mark_prices(underlying)
    
    # Hash mark prices for quick lookup
    mark_map = {m["symbol"]: m for m in mark_prices}
    
    board = []
    
    for t in tickers:
        sym = t["symbol"]
        mark_data = mark_map.get(sym, {})
        
        # Parses: BTC-240927-65000-C
        parts = sym.split("-")
        if len(parts) != 4:
            continue
            
        base = parts[0]
        expiry_str = parts[1]
        strike = float(parts[2])
        opt_type = parts[3]
        
        # Binance /eapi/v1/ticker provides 'openInterest' (contracts) directly.
        # 'amount' is 24h USD turnover — not the same as open interest.
        oi_contracts = float(t.get("openInterest", 0) or 0)
        vol_usd      = float(t.get("amount",       0) or 0)   # 24h USD volume
        vol_contracts= float(t.get("volume",       0) or 0)   # 24h contract volume

        # OI USD: contracts × spot price (NOT strike — strike biases OTM positions).
        # Binance eAPI /mark provides 'underlyingPrice' (spot) on the mark record.
        underlying_px = float(mark_data.get("underlyingPrice", 0) or 0)
        spot_proxy = underlying_px if underlying_px > 0 else 0.0

        if oi_contracts > 0:
            oi_usd = oi_contracts * (spot_proxy if spot_proxy > 0 else strike)
        elif vol_usd > 0:
            # Last resort: if OI missing entirely, use volume as weak proxy (flag this)
            oi_usd = vol_usd
            oi_contracts = vol_contracts
        else:
            oi_usd = 0.0


        # IV from markIV field (decimal, e.g. 0.65 = 65%)
        raw_iv = float(mark_data.get("markIV", 0) or 0)
        iv = raw_iv if 0 < raw_iv <= 5.0 else (raw_iv / 100.0 if raw_iv > 5.0 else 0.60)

        board.append({
            "symbol": sym,
            "underlying": base,
            "expiry_str": expiry_str,
            "strike": strike,
            "type": opt_type,
            "bid_price": float(t.get("bidPrice", 0) or 0),
            "ask_price": float(t.get("askPrice", 0) or 0),
            "open_interest": oi_contracts,
            "open_interest_usd": oi_usd,
            "volume": vol_usd,
            "mark_price": float(mark_data.get("markPrice", 0) or 0),
            "implied_volatility": iv,
        })
        
    return board
