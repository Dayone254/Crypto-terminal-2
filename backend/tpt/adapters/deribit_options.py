import logging
from typing import Any

import httpx

logger = logging.getLogger("tpt.adapters.deribit_options")

async def aggregate_options_board(underlying: str = "BTC") -> list[dict[str, Any]]:
    """
    Fetches the full options chain summary for a given currency (e.g. 'BTC' or 'ETH')
    from Deribit. Deribit provides superior density and avoids US regional IP blocks 
    that affect Binance eAPI.
    """
    url = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={underlying}&kind=option"
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=10.0)
            if response.status_code != 200:
                logger.error(f"Deribit API error: HTTP {response.status_code}")
                return []
                
            data = response.json()
            result_list = data.get("result", [])
            
            board = []
            for item in result_list:
                sym = item.get("instrument_name", "")
                
                # Parse: BTC-27SEP24-65000-C
                parts = sym.split("-")
                if len(parts) != 4:
                    continue
                    
                expiry_str = parts[1] # e.g. 27SEP24
                strike = float(parts[2])
                opt_type = parts[3]
                
                board.append({
                    "symbol": sym,
                    "underlying": underlying,
                    "expiry_str": expiry_str, # Will need slightly different parsing in options_flow if we want precise DTE
                    "strike": strike,
                    "type": opt_type,
                    "bid_price": float(item.get("bid_price", 0) or 0),
                    "ask_price": float(item.get("ask_price", 0) or 0),
                    "open_interest": float(item.get("open_interest", 0) or 0),
                    "volume": float(item.get("volume", 0) or 0),
                    "mark_price": float(item.get("mark_price", 0) or 0),
                    "underlying_price": float(item.get("underlying_price", 0) or 0),
                    "implied_volatility": float(item.get("mark_iv", 0) or 0) / 100.0 # Deribit gives IV as percentage (e.g. 55.2% -> 0.552)
                })
                
            return board
    except Exception as e:
        logger.error(f"Exception fetching Deribit options chain: {e}")
        return []
