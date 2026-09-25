"""Binance aggTrade WebSocket stream — yields executed spot trades for a symbol.

Each emitted dict has the shape:
    {
        "price":  float,   # execution price
        "qty":    float,   # base asset quantity (BTC)
        "usd":    float,   # notional USD value  (price * qty)
        "side":   "BUY" | "SELL",   # True = buyer was maker → aggressive sell
        "ts":     float,   # unix timestamp (seconds)
    }
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

BINANCE_WS_URL = "wss://stream.binance.com:9443/ws"
MAX_CONSECUTIVE_FAILURES = 5


def _spot_symbol(underlying: str) -> str:
    """Convert 'BTC' → 'btcusdt', 'ETH' → 'ethusdt'."""
    return f"{underlying.lower()}usdt"


async def stream_agg_trades(underlying: str) -> AsyncGenerator[dict[str, Any], None]:
    """
    Streams aggregated trade executions from Binance spot for *underlying*.
    Reconnects automatically up to MAX_CONSECUTIVE_FAILURES times.
    """
    symbol = _spot_symbol(underlying)
    url = f"{BINANCE_WS_URL}/{symbol}@aggTrade"
    failures = 0

    while True:
        try:
            logger.info("Connecting to Binance aggTrade WS: %s", url)
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                failures = 0
                logger.info("Connected to %s", url)

                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        # Binance aggTrade format:
                        # { "e":"aggTrade", "E":ms_ts, "s":"BTCUSDT",
                        #   "p":"82500.00", "q":"0.012",
                        #   "T":ms_trade_ts, "m": bool }
                        # m=True → buyer is maker → aggressive SELL
                        # m=False → buyer is taker → aggressive BUY
                        price = float(msg["p"])
                        qty   = float(msg["q"])
                        side  = "SELL" if msg.get("m", False) else "BUY"

                        yield {
                            "price": price,
                            "qty":   qty,
                            "usd":   price * qty,
                            "side":  side,
                            # Use Binance execution timestamp (ms→s), not server receive time.
                            # Server time.time() causes late-arrival trades to be bucketed into
                            # the wrong 5-minute rolling window under network lag.
                            "ts":    msg.get("T", msg.get("E", 0)) / 1000.0 or time.time(),
                        }
                    except (KeyError, ValueError, json.JSONDecodeError):
                        pass
                    except Exception as exc:
                        logger.error("aggTrade parse error: %s", exc)

        except asyncio.CancelledError:
            logger.info("aggTrade stream cancelled for %s", underlying)
            return
        except websockets.exceptions.ConnectionClosed as exc:
            logger.warning("aggTrade WS closed (%s): %s", underlying, exc)
        except Exception as exc:
            logger.error("aggTrade WS error (%s): %s", underlying, exc)

        failures += 1
        if failures > MAX_CONSECUTIVE_FAILURES:
            logger.error(
                "aggTrade stream for %s giving up after %d failures",
                underlying, failures - 1,
            )
            return

        wait = min(2 ** failures, 30)
        logger.warning("Reconnecting aggTrade for %s in %ds", underlying, wait)
        await asyncio.sleep(wait)
