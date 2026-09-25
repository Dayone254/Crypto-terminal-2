import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

import websockets

logger = logging.getLogger(__name__)

OKX_WS_URL = "wss://ws.okx.com:8443/ws/v5/public"
MAX_CONSECUTIVE_WS_FAILURES = 5

def format_okx_symbol(product_id: str) -> str:
    """Converts standard product_id (BTC-USD) to OKX instrument ID (BTC-USDT)."""
    return product_id.replace("-USD", "-USDT")

async def stream_okx_l2(product_id: str) -> AsyncGenerator[dict[str, Any], None]:
    """
    Connects to OKX WS v5 books channel for 40-depth orderbook streaming.
    Yields parsed top-20 orderbook depth dictionaries.
    """
    inst_id = format_okx_symbol(product_id)
    url = OKX_WS_URL
    subscribe_msg = {
        "op": "subscribe",
        "args": [{"channel": "books", "instId": inst_id}]
    }

    reconnect_attempts = 0
    bids_book: dict[float, float] = {}
    asks_book: dict[float, float] = {}

    while True:
        try:
            logger.info(f"Connecting to OKX WS L2: {url} ({inst_id})")
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                await ws.send(json.dumps(subscribe_msg))
                reconnect_attempts = 0
                logger.info(f"Subscribed to OKX books for {inst_id}")

                async for message in ws:
                    try:
                        data = json.loads(message)
                        if "data" not in data or not data["data"]:
                            continue

                        action = data.get("action")
                        item = data["data"][0]

                        if action == "snapshot":
                            bids_book.clear()
                            asks_book.clear()
                            for b in item.get("bids", []):
                                bids_book[float(b[0])] = float(b[1])
                            for a in item.get("asks", []):
                                asks_book[float(a[0])] = float(a[1])
                        else:
                            # Update / update deltas
                            for b in item.get("bids", []):
                                p, s = float(b[0]), float(b[1])
                                if s == 0:
                                    bids_book.pop(p, None)
                                else:
                                    bids_book[p] = s
                            for a in item.get("asks", []):
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
                        logger.error(f"Error processing OKX WS message: {e}")

        except asyncio.CancelledError:
            logger.info(f"OKX WS stream cancelled for {product_id}")
            break
        except Exception as e:
            logger.error(f"OKX WS connection error: {e}")

        reconnect_attempts += 1
        if reconnect_attempts > MAX_CONSECUTIVE_WS_FAILURES:
            logger.error(f"OKX WS for {product_id} giving up after {reconnect_attempts} failures")
            return

        sleep_time = min(2 ** reconnect_attempts, 30)
        await asyncio.sleep(sleep_time)
