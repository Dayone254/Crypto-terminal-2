import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

import websockets

logger = logging.getLogger(__name__)

COINBASE_WS_URL = "wss://ws-feed.exchange.coinbase.com"

async def stream_coinbase_l2(product_id: str) -> AsyncGenerator[dict[str, Any], None]:
    """
    Connects to Coinbase ws-feed level2 stream.
    Maintains a full local orderbook using snapshots and l2update diffs.
    Yields parsed partial orderbook (top 20 bids/asks) dictionaries periodically. 
    """
    url = COINBASE_WS_URL

    bids_book: dict[float, float] = {}
    asks_book: dict[float, float] = {}

    subscribe_msg = {
        "type": "subscribe",
        "product_ids": [product_id],
        "channels": ["level2"]
    }

    reconnect_attempts = 0
    while True:
        try:
            logger.info(f"Connecting to Coinbase WS L2: {url}")
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                await ws.send(json.dumps(subscribe_msg))
                reconnect_attempts = 0
                logger.info(f"Subscribed to Coinbase level2 for {product_id}")

                async for message in ws:
                    try:
                        data = json.loads(message)
                        msg_type = data.get("type")

                        if msg_type == "snapshot":
                            # Reset book
                            bids_book.clear()
                            asks_book.clear()
                            for b in data.get("bids", []):
                                bids_book[float(b[0])] = float(b[1])
                            for a in data.get("asks", []):
                                asks_book[float(a[0])] = float(a[1])

                            # Yield the snapshot immediately so the UI isn't empty
                            sorted_bids = sorted(bids_book.items(), key=lambda x: x[0], reverse=True)[:20]
                            sorted_asks = sorted(asks_book.items(), key=lambda x: x[0], reverse=False)[:20]
                            yield {
                                "bids": [[str(p), str(s)] for p, s in sorted_bids],
                                "asks": [[str(p), str(s)] for p, s in sorted_asks]
                            }

                        elif msg_type == "l2update":
                            changes = data.get("changes", [])
                            for side, price_str, size_str in changes:
                                p = float(price_str)
                                s = float(size_str)
                                if side == "buy":
                                    if s == 0:
                                        bids_book.pop(p, None)
                                    else:
                                        bids_book[p] = s
                                elif side == "sell":
                                    if s == 0:
                                        asks_book.pop(p, None)
                                    else:
                                        asks_book[p] = s
                                        
                            # After an update, yield top 20
                            sorted_bids = sorted(bids_book.items(), key=lambda x: x[0], reverse=True)[:20]
                            sorted_asks = sorted(asks_book.items(), key=lambda x: x[0], reverse=False)[:20]
                            
                            yield {
                                "bids": [[str(p), str(s)] for p, s in sorted_bids],
                                "asks": [[str(p), str(s)] for p, s in sorted_asks]
                            }

                    except json.JSONDecodeError:
                        pass
                    except Exception as e:
                        logger.error(f"Error processing Coinbase WS message: {e}")

        except asyncio.CancelledError:
            logger.info(f"Coinbase WS stream cancelled for {product_id}")
            break
        except Exception as e:
            logger.error(f"Coinbase WS connection error: {e}")

        reconnect_attempts += 1
        sleep_time = min(2 ** reconnect_attempts, 30)
        logger.info(f"Reconnecting to Coinbase WS in {sleep_time} seconds...")
        await asyncio.sleep(sleep_time)

