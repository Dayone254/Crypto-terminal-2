import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

import websockets

logger = logging.getLogger(__name__)

BINANCE_WS_URL = "wss://stream.binance.com:9443/ws"

def format_binance_symbol(product_id: str) -> str:
    """Converts Coinbase product_id (BTC-USD) to Binance symbol (btcusdt)."""
    # Simply replace -USD with USDT and make lowercase
    return product_id.replace("-USD", "USDT").lower()

async def stream_binance_l2(product_id: str) -> AsyncGenerator[dict[str, Any], None]:
    """
    Connects to Binance @depth20@100ms stream for the given product.
    Yields parsed partial orderbook (top 20 bids/asks) dictionaries.
    """
    symbol = format_binance_symbol(product_id)
    stream_name = f"{symbol}@depth20@100ms"
    url = f"{BINANCE_WS_URL}/{stream_name}"
    
    reconnect_attempts = 0
    while True:
        try:
            logger.info(f"Connecting to Binance WS L2 Depth: {url}")
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                reconnect_attempts = 0
                logger.info(f"Connected to {url}")
                
                async for message in ws:
                    try:
                        data = json.loads(message)
                        # Binance partial book format:
                        # {
                        #   "lastUpdateId": 160,
                        #   "bids": [ [ "4.00000000", "431.00000000" ] ],
                        #   "asks": [ [ "4.00000200", "12.00000000" ] ]
                        # }
                        if "bids" in data and "asks" in data:
                            yield data
                    except json.JSONDecodeError:
                        logger.error("Failed to decode Binance WS message")
                    except Exception as e:
                        logger.error(f"Error processing Binance WS message: {e}")
        except asyncio.CancelledError:
            logger.info(f"Binance WS stream cancelled for {product_id}")
            break
        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"Binance WS connection closed: {e}")
        except Exception as e:
            logger.error(f"Binance WS connection error: {e}")
            
        reconnect_attempts += 1
        sleep_time = min(2 ** reconnect_attempts, 30)
        logger.info(f"Reconnecting to Binance WS in {sleep_time} seconds...")
        await asyncio.sleep(sleep_time)

