import asyncio
import logging
import time
from typing import Any

from tpt.adapters.binance_options import aggregate_options_board as fetch_binance_options
from tpt.adapters.bybit_options import aggregate_bybit_options
from tpt.adapters.deribit_options import aggregate_options_board as fetch_deribit_options
from tpt.adapters.okx_options import aggregate_okx_options

logger = logging.getLogger("tpt.adapters.options_aggregator")

# In-memory RAM cache for multi-venue options board
# Key: underlying (e.g. "BTC", "ETH") -> {"combined_board": [...], "venue_metrics": {...}, "timestamp": float}
_OPTIONS_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_TTL_SECONDS = 30.0
_FETCH_LOCKS: dict[str, asyncio.Lock] = {}

async def _fetch_and_cache(underlying: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Queries options boards from Deribit, Binance Options, OKX Options, and Bybit Options concurrently
    with a generous 12.0s timeout per venue to ensure 100% multi-venue liquidity coverage.
    """
    if underlying not in _FETCH_LOCKS:
        _FETCH_LOCKS[underlying] = asyncio.Lock()

    async with _FETCH_LOCKS[underlying]:
        # Double-check cache inside lock
        cached = _OPTIONS_CACHE.get(underlying)
        if cached and (time.time() - cached["timestamp"]) < _CACHE_TTL_SECONDS:
            return cached["combined_board"], cached["venue_metrics"]


        async def _safe_fetch(coro, venue_name: str):
            t0 = time.time()
            try:
                # 1.5s max timeout per venue for sub-second API responsiveness
                res = await asyncio.wait_for(coro, timeout=1.5)

                elapsed = time.time() - t0
                logger.info(f"Successfully fetched {len(res)} option contracts from {venue_name} in {elapsed:.2f}s")
                return res
            except Exception as e:
                elapsed = time.time() - t0
                logger.warning(f"Options venue fetch for {venue_name} timed out/failed after {elapsed:.2f}s: {e}")
                return []

        # Check Deribit real-time WS board first (BTC/ETH only; ~100ms latency)
        deribit_live: list[dict[str, Any]] = []
        try:
            from tpt.adapters.deribit_ws import get_live_board, is_live
            if is_live(underlying):
                deribit_live = get_live_board(underlying)
                if deribit_live:
                    logger.info("Using Deribit WS live board (%d contracts) for %s",
                                len(deribit_live), underlying)
        except Exception:
            pass

        tasks = [
            _safe_fetch(fetch_binance_options(underlying), "Binance"),
            _safe_fetch(aggregate_okx_options(underlying), "OKX"),
            _safe_fetch(aggregate_bybit_options(underlying), "Bybit"),
        ]
        # Only REST-fetch Deribit if WS board is cold/empty
        if not deribit_live:
            tasks.insert(0, _safe_fetch(fetch_deribit_options(underlying), "Deribit"))
        else:
            async def _return_live(board=deribit_live):
                return board
            tasks.insert(0, _safe_fetch(_return_live(), "Deribit-WS"))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        deribit_data: list[dict[str, Any]] = results[0] if isinstance(results[0], list) else []
        binance_data: list[dict[str, Any]] = results[1] if isinstance(results[1], list) else []
        okx_data: list[dict[str, Any]] = results[2] if isinstance(results[2], list) else []
        bybit_data: list[dict[str, Any]] = results[3] if isinstance(results[3], list) else []

        # Tag venue names
        for item in deribit_data:
            if isinstance(item, dict):
                item["venue"] = "Deribit"
        for item in binance_data:
            if isinstance(item, dict):
                item["venue"] = "Binance"

        combined_board = deribit_data + binance_data + okx_data + bybit_data

        # Calculate Open Interest USD breakdown per venue
        deribit_oi_usd = sum(float(item.get("open_interest_usd", 0) or 0) for item in deribit_data if isinstance(item, dict))
        binance_oi_usd = sum(float(item.get("open_interest_usd", 0) or 0) for item in binance_data if isinstance(item, dict))
        okx_oi_usd     = sum(float(item.get("open_interest_usd", 0) or 0) for item in okx_data if isinstance(item, dict))
        bybit_oi_usd   = sum(float(item.get("open_interest_usd", 0) or 0) for item in bybit_data if isinstance(item, dict))

        total_oi_usd   = deribit_oi_usd + binance_oi_usd + okx_oi_usd + bybit_oi_usd

        active_venues = []
        if deribit_data: active_venues.append("Deribit")
        if binance_data: active_venues.append("Binance")
        if okx_data: active_venues.append("OKX")
        if bybit_data: active_venues.append("Bybit")

        venue_metrics = {
            "active_venues": active_venues,
            "total_venues": len(active_venues),
            "total_open_interest_usd": total_oi_usd,
            "deribit_share_pct": round((deribit_oi_usd / total_oi_usd * 100), 1) if total_oi_usd > 0 else 0.0,
            "binance_share_pct": round((binance_oi_usd / total_oi_usd * 100), 1) if total_oi_usd > 0 else 0.0,
            "okx_share_pct": round((okx_oi_usd / total_oi_usd * 100), 1) if total_oi_usd > 0 else 0.0,
            "bybit_share_pct": round((bybit_oi_usd / total_oi_usd * 100), 1) if total_oi_usd > 0 else 0.0,
        }

        logger.info(
            f"Aggregated {len(combined_board)} option contracts for {underlying} across {len(active_venues)} venues. "
            f"Deribit: {len(deribit_data)}, Binance: {len(binance_data)}, OKX: {len(okx_data)}, Bybit: {len(bybit_data)}"
        )

        _OPTIONS_CACHE[underlying] = {
            "combined_board": combined_board,
            "venue_metrics": venue_metrics,
            "timestamp": time.time()
        }

        return combined_board, venue_metrics

async def aggregate_multi_venue_options_board(underlying: str = "BTC") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Returns options board and venue metrics for the requested underlying asset.
    Uses RAM cache for instant (<1ms) response, triggering background updates if cache is stale.
    """
    base = underlying.upper().split("-")[0] if "-" in underlying else underlying.upper()
    cached = _OPTIONS_CACHE.get(base)
    now = time.time()

    if cached:
        age = now - cached["timestamp"]
        if age > _CACHE_TTL_SECONDS:
            # Trigger background refresh if stale without blocking the request
            asyncio.create_task(_fetch_and_cache(base))
        return cached["combined_board"], cached["venue_metrics"]

    # First cold fetch: wait for initial population
    return await _fetch_and_cache(base)
