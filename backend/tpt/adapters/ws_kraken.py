import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

import websockets

logger = logging.getLogger(__name__)

KRAKEN_WS_URL = "wss://ws.kraken.com"
MAX_CONSECUTIVE_WS_FAILURES = 5

def format_kraken_symbol(product_id: str) -> str:
    """Converts standard symbol (BTC-USD) to Kraken WS symbol pair (XBT/USD)."""
    base, quote = product_id.split("-")
    if base == "BTC":
        base = "XBT"
    return f"{base}/{quote}"

async def stream_kraken_l2(product_id: str) -> AsyncGenerator[dict[str, Any], None]:
    """
    Connects to Kraken WS v1 book channel for depth.
    Yields parsed top-20 orderbook depth dictionaries.
    """
    symbol = format_kraken_symbol(product_id)
    url = KRAKEN_WS_URL
    subscribe_msg = {
        "event": "subscribe",
        "pair": [symbol],
        "subscription": {"name": "book", "depth": 25}
    }

    reconnect_attempts = 0
    bids_book: dict[float, float] = {}
    asks_book: dict[float, float] = {}

    while True:
        try:
            logger.info(f"Connecting to Kraken WS L2: {url} ({symbol})")
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                await ws.send(json.dumps(subscribe_msg))
                reconnect_attempts = 0
                logger.info(f"Subscribed to Kraken book for {symbol}")

                async for message in ws:
                    try:
                        data = json.loads(message)
                        if isinstance(data, dict):
                            # Heartbeats or status events
                            continue

                        if isinstance(data, list) and len(data) >= 4:
                            channel_data = data[1]

                            # Snapshot vs Delta update
                            if "bs" in channel_data or "as" in channel_data:
                                # Snapshot
                                bids_book.clear()
                                asks_book.clear()
                                for b in channel_data.get("bs", []):
                                    bids_book[float(b[0])] = float(b[1])
                                for a in channel_data.get("as", []):
                                    asks_book[float(a[0])] = float(a[1])
                            else:
                                # Update
                                if "b" in channel_data:
                                    for b in channel_data["b"]:
                                        p, s = float(b[0]), float(b[1])
                                        if s == 0:
                                            bids_book.pop(p, None)
                                        else:
                                            bids_book[p] = s
                                if "a" in channel_data:
                                    for a in channel_data["a"]:
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
                        logger.error(f"Error processing Kraken WS message: {e}")

        except asyncio.CancelledError:
            logger.info(f"Kraken WS stream cancelled for {product_id}")
            break
        except Exception as e:
            logger.error(f"Kraken WS connection error: {e}")

        reconnect_attempts += 1
        if reconnect_attempts > MAX_CONSECUTIVE_WS_FAILURES:
            logger.error(f"Kraken WS for {product_id} giving up after {reconnect_attempts} failures")
            return

        sleep_time = min(2 ** reconnect_attempts, 30)
        await asyncio.sleep(sleep_time)
