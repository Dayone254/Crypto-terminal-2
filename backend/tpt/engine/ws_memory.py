import asyncio
import logging
from typing import Any

from tpt.config.settings import settings
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
        self._orderflow_tasks: dict[str, asyncio.Task] = {}  # per-underlying trade stream tasks

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

    async def subscribe(self, product_ids: list[str], max_symbols: int | None = None):
        """Expand subscriptions dynamically, up to a hard cap.

        Each symbol costs three sockets: Binance L2, Coinbase L2 and a ticker
        stream. Subscribing to every scored symbol (100+) exhausted the event
        loop's file descriptors — `ValueError: too many file descriptors in
        select()` — which killed the whole server mid-scan. The set is therefore
        capped (see settings.max_ws_subscriptions).
        """
        cap = max_symbols if max_symbols is not None else settings.max_ws_subscriptions
        capped = False

        if not settings.enable_live_ws:
            logger.info(
                "Live WS disabled (ENABLE_LIVE_WS=false); using REST L2 snapshots for %d symbol(s).",
                len(product_ids),
            )
            return

        for pid in product_ids:
            if pid in self._active_symbols:
                continue
            if len(self._active_symbols) >= cap:
                capped = True
                continue

            self._active_symbols.add(pid)
            self.l2_books[pid] = {"bids": [], "asks": []}
            self.tickers[pid] = {}

            # Start consuming loops
            t_l2 = asyncio.create_task(self._consume_l2(pid))
            t_tick = asyncio.create_task(self._consume_ticker(pid))
            self._tasks[pid] = (t_l2, t_tick)

            # Sleep briefly to avoid connection burst rate-limits
            await asyncio.sleep(0.1)

        if capped:
            logger.warning(
                "WS subscription cap (%d symbols) reached; %d requested symbol(s) skipped. "
                "Raise MAX_WS_SUBSCRIPTIONS to hold more live buffers.",
                cap,
                len(product_ids) - len(self._active_symbols),
            )

    def start_options_daemon(self) -> asyncio.Task:
        """Start the macro options-flow refresh loop AND the orderflow trade streams.

        Deliberately independent of L2 subscriptions: options gamma/IV-skew for
        BTC/ETH must keep working even when live WebSocket streaming is disabled.
        """
        if self._options_task is None or self._options_task.done():
            self._options_task = asyncio.create_task(self._sync_options_flow())

        # Launch rolling orderflow accumulators for BTC and ETH
        for underlying in ("BTC", "ETH"):
            task = self._orderflow_tasks.get(underlying)
            if task is None or task.done():
                from tpt.engine.orderflow_accumulator import run_orderflow_stream
                self._orderflow_tasks[underlying] = asyncio.create_task(
                    run_orderflow_stream(underlying)
                )
                logger.info("Orderflow stream task started for %s", underlying)

        # Launch Deribit real-time WebSocket board streamers (BTC + ETH only)
        if settings.enable_live_ws:
            try:
                from tpt.adapters.deribit_ws import start_deribit_ws_streams
                start_deribit_ws_streams(["BTC", "ETH"])
                logger.info("Deribit WS stream tasks launched for BTC, ETH")
            except Exception as dws_e:
                logger.warning("Deribit WS stream failed to start: %s", dws_e)

        return self._options_task

    async def _sync_options_flow(self):
        """Background loop caching Deribit/Multi-Venue Options Flow every 15 seconds.
        Runs immediately on startup so fresh data is always available."""
        from tpt.engine.options_flow import calculate_macro_gamma_exposure
        # Yield briefly so FastAPI lifespan finishes startup cleanly
        await asyncio.sleep(2.0)
        while True:
            try:
                for underlying in ("BTC", "ETH"):
                    try:
                        flow = await asyncio.wait_for(calculate_macro_gamma_exposure(underlying, 0.0), timeout=15.0)
                        if flow:
                            self.macro_options_cache[underlying] = flow
                    except Exception as sym_e:
                        logger.warning(f"Options sync error for {underlying}: {sym_e}")
                    await asyncio.sleep(0.1)  # Yield to event loop between underlying assets
                logger.info("Successfully updated global Macro Options memory cache for BTC, ETH.")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Macro Options Daemon Sync Error: {e}")
            await asyncio.sleep(20)



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
