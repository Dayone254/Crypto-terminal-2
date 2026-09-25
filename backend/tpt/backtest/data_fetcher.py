"""Historical data expansion fetcher — fetches up to 20 years of OHLCV history.

The actual data depth is determined by Coinbase's availability (BTC from ~2015,
most alts from 2020+). The fetcher stops automatically when the exchange returns
fewer than 5 candles for a time window.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from tpt.adapters.coinbase import CoinbaseAdapter
from tpt.backtest.storage import (
    SURVIVORSHIP_BIAS_NOTE,
    save_historical_candles_sync,
)

logger = logging.getLogger(__name__)

# Standard timeframe mapping in seconds
TIMEFRAME_SECONDS = {
    3600: 3600,       # 1h
    86400: 86400,     # 1d
    900: 900,         # 15m
    21600: 21600,     # 6h
}


async def fetch_symbol_history_chunked(
    symbol: str,
    granularity: int = 900,
    years: float = 20.0,
    adapter: CoinbaseAdapter | None = None,
) -> int:
    """Fetch up to `years` of historical OHLCV candles for a single symbol using time pagination.
    
    Coinbase returns max 300 candles per call. We step backward in chunks of 300 * granularity seconds.
    Saves batches into SQLite via storage manager.
    """
    own_adapter = adapter is None
    if adapter is None:
        adapter = CoinbaseAdapter()

    total_inserted = 0
    now_dt = datetime.now(UTC)
    start_boundary_dt = now_dt - timedelta(days=int(years * 365))
    
    current_end_dt = now_dt
    chunk_span_seconds = 300 * granularity

    try:
        while current_end_dt > start_boundary_dt:
            current_start_dt = current_end_dt - timedelta(seconds=chunk_span_seconds)
            if current_start_dt < start_boundary_dt:
                current_start_dt = start_boundary_dt

            start_iso = current_start_dt.isoformat()
            end_iso = current_end_dt.isoformat()

            try:
                candles = await adapter.get_candles(
                    symbol,
                    granularity=granularity,
                    start=start_iso,
                    end=end_iso,
                    limit=300,
                )
                if candles and isinstance(candles, list):
                    saved = save_historical_candles_sync(symbol, granularity, candles)
                    total_inserted += saved
                    if len(candles) < 5:
                        # Reached start of symbol history
                        logger.info("Reached historical listing bound for %s at %s", symbol, start_iso)
                        break
                else:
                    # Empty response or error
                    break
            except Exception as exc:
                logger.warning("Error fetching chunk for %s (%s to %s): %s", symbol, start_iso, end_iso, exc)
                break

            current_end_dt = current_start_dt - timedelta(seconds=1)
            await asyncio.sleep(0.1)  # Gentle rate limiting

    finally:
        if own_adapter:
            await adapter.close()

    return total_inserted


async def expand_universe_history(
    symbols: list[str],
    granularity: int = 900,
    years: float = 20.0,
    max_concurrent: int = 3,
) -> dict[str, Any]:
    """Expand historical OHLCV dataset across a scan universe up to `years` of history.
    
    Surfaces survivorship bias limitation note in return metadata.
    """
    logger.info("Starting historical data expansion for %d symbols over %.1f years", len(symbols), years)
    adapter = CoinbaseAdapter()
    results = {}
    sem = asyncio.Semaphore(max_concurrent)

    async def _worker(sym: str):
        async with sem:
            count = await fetch_symbol_history_chunked(sym, granularity=granularity, years=years, adapter=adapter)
            results[sym] = count

    try:
        await asyncio.gather(*[_worker(s) for s in symbols], return_exceptions=True)
    finally:
        await adapter.close()

    total_candles = sum(v for v in results.values() if isinstance(v, int))
    return {
        "symbols_processed": len(symbols),
        "total_candles_fetched": total_candles,
        "symbol_breakdown": results,
        "survivorship_bias_note": SURVIVORSHIP_BIAS_NOTE,
    }
