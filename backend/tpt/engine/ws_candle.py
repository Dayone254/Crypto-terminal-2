"""Real-time Coinbase ticker WebSocket stream.

Connects to the Coinbase Advanced Trade WebSocket and emits
price tick events for a given product, suitable for animating
the rightmost candle in the lightweight-charts NativeChart component.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

import websockets

logger = logging.getLogger(__name__)

COINBASE_WS_URL = "wss://advanced-trade-ws.coinbase.com"

# Give up after this many consecutive connection failures instead of retrying
# forever. A blocked WebSocket path otherwise turns into a permanent handshake
# storm that saturates the event loop.
MAX_CONSECUTIVE_WS_FAILURES = 5


async def stream_ticker(product_id: str) -> AsyncGenerator[dict[str, Any], None]:
    """Stream real-time ticker ticks for `product_id`.

    Yields dicts:  { price: float, time: int (unix seconds), volume: float }
    """
    subscribe_msg = json.dumps({
        "type": "subscribe",
        "product_ids": [product_id],
        "channel": "ticker",
    })

    attempts = 0
    while True:
        try:
            async with websockets.connect(COINBASE_WS_URL, ping_interval=20) as ws:
                await ws.send(subscribe_msg)
                attempts = 0
                logger.info("Ticker WebSocket subscribed for %s", product_id)

                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        # Coinbase Advanced Trade format: events list
                        for event in msg.get("events", []):
                            for tick in event.get("tickers", []):
                                price = float(tick.get("price", 0))
                                volume = float(tick.get("volume_24_h", 0))
                                if price > 0:
                                    yield {
                                        "price": price,
                                        "volume": volume,
                                        "time": int(time.time()),  # Unix epoch seconds (was: event loop uptime)
                                    }
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue

        except asyncio.CancelledError:
            logger.info("Ticker stream cancelled for %s", product_id)
            return
        except Exception as e:
            attempts += 1
            if attempts > MAX_CONSECUTIVE_WS_FAILURES:
                logger.error(
                    "Ticker stream for %s giving up after %d consecutive failures: %s",
                    product_id,
                    attempts - 1,
                    e,
                )
                return
            backoff = min(2 ** attempts, 30)
            logger.warning(
                "Ticker stream error for %s: %s — reconnecting in %ds (attempt %d/%d)",
                product_id,
                e,
                backoff,
                attempts,
                MAX_CONSECUTIVE_WS_FAILURES,
            )
            await asyncio.sleep(backoff)
