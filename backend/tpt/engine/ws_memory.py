import asyncio
import logging
from typing import Any

from tpt.engine.l2_multiplexer import stream_multiplexed_l2
from tpt.engine.ws_candle import stream_ticker

logger = logging.getLogger(__name__)

class BackgroundMemoryStore:
    """Thread-safe, non-blocking memory dictionary holding live WebSocket streams."""
    def __init__(self):
        self.l2_books: dict[str, dict[str, Any]] = {}
        self.tickers: dict[str, dict[str, Any]] = {}
        # Changed from flat list to Dict mapping pid to its tuple of tasks
        self._tasks: dict[str, tuple[asyncio.Task, asyncio.Task]] = {}
        self._active_symbols: set[str] = set()
        self.macro_options_cache: dict[str, Any] = {}
        self._options_task: asyncio.Task | None = None

    def get_l2(self, product_id: str) -> dict[str, Any] | None:
        """Returns the latest parsed L2 order book geometry."""
        return self.l2_books.get(product_id)

    def get_ticker(self, product_id: str) -> dict[str, Any] | None:
        """Returns the latest price tick."""
        return self.tickers.get(product_id)

    def get_macro_options(self, underlying: str) -> dict[str, Any] | None:
        """Returns the cached Gamma engine state for BTC/ETH to power the AI Score."""
        return self.macro_options_cache.get(underlying.upper())

    async def _consume_l2(self, product_id: str):
        try:
            async for data in stream_multiplexed_l2(product_id):
                self.l2_books[product_id] = data
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"L2 Buffer Error for {product_id}: {e}")

    async def _consume_ticker(self, product_id: str):
        try:
            async for data in stream_ticker(product_id):
                self.tickers[product_id] = data
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Ticker Buffer Error for {product_id}: {e}")

    async def subscribe(self, product_ids: list[str]):
        """Expand subscriptions dynamically."""
        for pid in product_ids:
            if pid not in self._active_symbols:
                self._active_symbols.add(pid)
                self.l2_books[pid] = {"bids": [], "asks": []}
                self.tickers[pid] = {}
                
                # Start consuming loops
                t_l2 = asyncio.create_task(self._consume_l2(pid))
                t_tick = asyncio.create_task(self._consume_ticker(pid))
                self._tasks[pid] = (t_l2, t_tick)
                
                # Sleep briefly to avoid connection burst rate-limits
                await asyncio.sleep(0.1)
                
        # Start options daemon lazily if not running
        if self._options_task is None:
            self._options_task = asyncio.create_task(self._sync_options_flow())

    async def _sync_options_flow(self):
        """Background loop caching Deribit Options Flow precisely every 5 minutes."""
        from tpt.engine.options_flow import calculate_macro_gamma_exposure
        while True:
            try:
                btc_flow = await calculate_macro_gamma_exposure("BTC", 0.0)
                eth_flow = await calculate_macro_gamma_exposure("ETH", 0.0)
                if btc_flow:
                    self.macro_options_cache["BTC"] = btc_flow
                if eth_flow:
                    self.macro_options_cache["ETH"] = eth_flow
                logger.info("Successfully updated global Macro Options memory cache.")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Macro Options Daemon Sync Error: {e}")
            await asyncio.sleep(300)

    async def sync_active_universe(self, current_product_ids: list[str]):
        """Cancel streams for symbols no longer in the active list to prevent unbounded task leaks."""
        current_set = set(current_product_ids)
        orphans = self._active_symbols - current_set
        
        for pid in orphans:
            self._active_symbols.remove(pid)
            if pid in self._tasks:
                t1, t2 = self._tasks.pop(pid)
                t1.cancel()
                t2.cancel()
            self.l2_books.pop(pid, None)
            self.tickers.pop(pid, None)
            logger.info(f"Unsubscribed WS streams for dormant symbol: {pid}")
            # Yield to loop so cancellations propagate cleanly
            await asyncio.sleep(0)

    def shutdown(self):
        """Cancel all stream consumers."""
        for t1, t2 in self._tasks.values():
            t1.cancel()
            t2.cancel()
        self._tasks.clear()
        self._active_symbols.clear()
        self.l2_books.clear()
        self.tickers.clear()

# Global Singleton Fast Buffer
ws_memory = BackgroundMemoryStore()
