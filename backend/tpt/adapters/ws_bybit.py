import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

import websockets

logger = logging.getLogger(__name__)

BYBIT_WS_URL = "wss://stream.bybit.com/v5/public/spot"
MAX_CONSECUTIVE_WS_FAILURES = 5

def format_bybit_symbol(product_id: str) -> str:
    """Converts standard product_id (BTC-USD) to Bybit symbol (BTCUSDT)."""
    return product_id.replace("-USD", "USDT")

async def stream_bybit_l2(product_id: str) -> AsyncGenerator[dict[str, Any], None]:
    """
    Connects to Bybit WS v5 orderbook.50 stream.
    Yields parsed top-20 orderbook depth dictionaries.
    """
    symbol = format_bybit_symbol(product_id)
    url = BYBIT_WS_URL
    topic = f"orderbook.50.{symbol}"
    subscribe_msg = {
        "op": "subscribe",
        "args": [topic]
    }

    reconnect_attempts = 0
    bids_book: dict[float, float] = {}
    asks_book: dict[float, float] = {}

    while True:
        try:
            logger.info(f"Connecting to Bybit WS L2: {url} ({symbol})")
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                await ws.send(json.dumps(subscribe_msg))
                reconnect_attempts = 0
                logger.info(f"Subscribed to Bybit orderbook for {symbol}")

                async for message in ws:
                    try:
                        data = json.loads(message)
                        if "data" not in data or data.get("topic") != topic:
                            continue

                        item = data["data"]
                        msg_type = data.get("type")

                        if msg_type == "snapshot":
                            bids_book.clear()
                            asks_book.clear()
                            for b in item.get("b", []):
                                bids_book[float(b[0])] = float(b[1])
                            for a in item.get("a", []):
                                asks_book[float(a[0])] = float(a[1])
                        else:
                            # Delta updates
                            for b in item.get("b", []):
                                p, s = float(b[0]), float(b[1])
                                if s == 0:
                                    bids_book.pop(p, None)
                                else:
                                    bids_book[p] = s
                            for a in item.get("a", []):
                                p, s = float(a[0]), float(a[1])
                                if s == 0:
                                    asks_book.pop(p, None)
                                else:
                                    asks_book[p] = s

                        sorted_bids = sorted(bids_book.items(), key=lambda x: x[0], reverse=True)[:20]
                        sorted_asks = sorted(asks_book.items(), key=lambda x: x[0], reverse=False)[:20]

                        yield {
                            "bids": [[str(p), str(s)] for p, s in sorted_bids],
                            "asks": [[str(p), str(s)] for p, s in sorted_asks]
                        }
                    except (json.JSONDecodeError, ValueError, KeyError):
                        pass
                    except Exception as e:
                        logger.error(f"Error processing Bybit WS message: {e}")

        except asyncio.CancelledError:
            logger.info(f"Bybit WS stream cancelled for {product_id}")
            break
        except Exception as e:
            logger.error(f"Bybit WS connection error: {e}")

        reconnect_attempts += 1
        if reconnect_attempts > MAX_CONSECUTIVE_WS_FAILURES:
            logger.error(f"Bybit WS for {product_id} giving up after {reconnect_attempts} failures")
            return

        sleep_time = min(2 ** reconnect_attempts, 30)
        await asyncio.sleep(sleep_time)
