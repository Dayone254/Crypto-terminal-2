import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import Any

from tpt.adapters.ws_binance import stream_binance_l2
from tpt.adapters.ws_bybit import stream_bybit_l2
from tpt.adapters.ws_coinbase import stream_coinbase_l2
from tpt.adapters.ws_kraken import stream_kraken_l2
from tpt.adapters.ws_okx import stream_okx_l2

logger = logging.getLogger(__name__)

SUPPORTED_EXCHANGES = ["coinbase", "binance", "kraken", "okx", "bybit"]

async def stream_multiplexed_l2(
    product_id: str,
    exchanges: list[str] | None = None
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Multiplexes L2 depth streams across Coinbase, Binance, Kraken, OKX, and Bybit
    into a single real-time aggregated liquidity book.
    """
    target_exchanges = exchanges or SUPPORTED_EXCHANGES
    queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()

    tasks: list[asyncio.Task] = []

    async def make_consumer(name: str, stream_fn):
        try:
            async for data in stream_fn(product_id):
                await queue.put((name, data))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"{name.capitalize()} consumer error: {e}")

    # Launch streams for configured exchanges
    adapters = {
        "coinbase": stream_coinbase_l2,
        "binance": stream_binance_l2,
        "kraken": stream_kraken_l2,
        "okx": stream_okx_l2,
        "bybit": stream_bybit_l2,
    }

    for name in target_exchanges:
        if name in adapters:
            tasks.append(asyncio.create_task(make_consumer(name, adapters[name])))

    books: dict[str, dict[str, list[Any]]] = {
        name: {"bids": [], "asks": []} for name in target_exchanges
    }

    try:
        while True:
            exchange, data = await queue.get()
            books[exchange] = data

            # Aggregate across all active venues
            agg_bids: dict[float, float] = {}
            agg_asks: dict[float, float] = {}
            active_venues: set[str] = set()

            for ex_name, book in books.items():
                if book.get("bids") or book.get("asks"):
                    active_venues.add(ex_name)

                for price_str, qty_str in book.get("bids", []):
                    try:
                        p, q = float(price_str), float(qty_str)
                        agg_bids[p] = agg_bids.get(p, 0.0) + q
                    except (ValueError, TypeError):
                        continue

                for price_str, qty_str in book.get("asks", []):
                    try:
                        p, q = float(price_str), float(qty_str)
                        agg_asks[p] = agg_asks.get(p, 0.0) + q
                    except (ValueError, TypeError):
                        continue

            sorted_bids = sorted(agg_bids.items(), key=lambda x: x[0], reverse=True)[:20]
            sorted_asks = sorted(agg_asks.items(), key=lambda x: x[0], reverse=False)[:20]

            yield {
                "bids": [[str(p), str(q)] for p, q in sorted_bids],
                "asks": [[str(p), str(q)] for p, q in sorted_asks],
                "active_exchanges": list(active_venues),
                "total_venues": len(active_venues)
            }

    except asyncio.CancelledError:
        logger.info(f"Multiplexed L2 stream cancelled for {product_id}")
    finally:
        for t in tasks:
            t.cancel()
