import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import Any

from tpt.adapters.ws_binance import stream_binance_l2
from tpt.adapters.ws_coinbase import stream_coinbase_l2

logger = logging.getLogger(__name__)

async def stream_multiplexed_l2(product_id: str) -> AsyncGenerator[dict[str, Any], None]:
    """
    Multiplexes Binance and Coinbase L2 streams into a single aggregated feed.
    """
    queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()

    async def consume_binance():
        try:
            async for data in stream_binance_l2(product_id):
                await queue.put(("binance", data))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Binance consumer error: {e}")

    async def consume_coinbase():
        try:
            async for data in stream_coinbase_l2(product_id):
                await queue.put(("coinbase", data))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Coinbase consumer error: {e}")

    t1 = asyncio.create_task(consume_binance())
    t2 = asyncio.create_task(consume_coinbase())

    books: dict[str, dict[str, list[Any]]] = {
        "binance": {"bids": [], "asks": []},
        "coinbase": {"bids": [], "asks": []}
    }

    try:
        while True:
            exchange, data = await queue.get()
            books[exchange] = data

            # Fast aggregate
            agg_bids: dict[float, float] = {}
            agg_asks: dict[float, float] = {}

            # Binance
            for price_str, qty_str in books["binance"].get("bids", []):
                p, q = float(price_str), float(qty_str)
                agg_bids[p] = agg_bids.get(p, 0) + q
            for price_str, qty_str in books["binance"].get("asks", []):
                p, q = float(price_str), float(qty_str)
                agg_asks[p] = agg_asks.get(p, 0) + q

            # Coinbase
            for price_str, qty_str in books["coinbase"].get("bids", []):
                p, q = float(price_str), float(qty_str)
                agg_bids[p] = agg_bids.get(p, 0) + q
            for price_str, qty_str in books["coinbase"].get("asks", []):
                p, q = float(price_str), float(qty_str)
                agg_asks[p] = agg_asks.get(p, 0) + q

            sorted_bids = sorted(agg_bids.items(), key=lambda x: x[0], reverse=True)[:20]
            sorted_asks = sorted(agg_asks.items(), key=lambda x: x[0], reverse=False)[:20]

            yield {
                "bids": [[str(p), str(q)] for p, q in sorted_bids],
                "asks": [[str(p), str(q)] for p, q in sorted_asks]
            }
            
    except asyncio.CancelledError:
        logger.info(f"Multiplexed L2 stream cancelled for {product_id}")
    finally:
        t1.cancel()
        t2.cancel()

