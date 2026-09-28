"""Catalyst watchlist boost — thin async interface for the main scorer.

Usage in scorer.py:
    from tpt.catalyst.watchlist_boost import get_catalyst_boost
    boost = await get_catalyst_boost(symbol)          # returns float [0.0, 15.0]
    macro_ix += boost
    if boost > 0:
        components_dump["catalyst_boost"] = boost

The boost is drawn from the latest unexpired DB row for the symbol.
Falls back to 0.0 silently if the catalyst table has no data yet.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# In-memory cache: symbol -> (boost, expires_unixtime)
# Prevents a DB round-trip on every scorer call (scorer is called ~400x per scan cycle)
_cache: dict[str, tuple[float, float]] = {}

_CACHE_TTL_SECONDS = 600.0  # 10 minutes


def _cache_hit(symbol: str) -> float | None:
    entry = _cache.get(symbol)
    if entry is None:
        return None
    boost, expires = entry
    if datetime.now(timezone.utc).timestamp() < expires:
        return boost
    del _cache[symbol]
    return None


def _set_cache(symbol: str, boost: float) -> None:
    expires = datetime.now(timezone.utc).timestamp() + _CACHE_TTL_SECONDS
    _cache[symbol] = (boost, expires)


def update_cache(symbol: str, boost: float) -> None:
    """Warm the cache with a freshly-scraped boost.

    Called by the catalyst daemon after each successful scrape. Without this the
    cache was only ever populated by `get_catalyst_boost` — which nobody calls —
    so the scorer's sync read returned 0.0 forever while the daemon periodically
    *cleared* the cache it never filled.
    """
    _set_cache(symbol, float(boost or 0.0))


def get_catalyst_boost_sync(symbol: str) -> float:
    """Return the cached catalyst boost for a symbol WITHOUT hitting the DB.

    Safe to call from synchronous contexts (e.g. scorer.py running inside
    asyncio.to_thread).  Returns 0.0 if the cache is empty or stale.
    """
    cached = _cache_hit(symbol)
    return cached if cached is not None else 0.0


async def get_catalyst_boost(symbol: str) -> float:
    """Return the catalyst scorer boost [0.0, 15.0] for the given symbol.

    Tries in-memory cache first.  On a miss, queries the DB.
    Returns 0.0 if no active catalyst signal exists.
    """
    cached = _cache_hit(symbol)
    if cached is not None:
        return cached

    try:
        from tpt.db.connection import AsyncSessionLocal
        from tpt.db.models import CatalystSignal
        from sqlalchemy import select

        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            row = await db.execute(
                select(CatalystSignal.scorer_boost, CatalystSignal.priority_tier)
                .where(CatalystSignal.symbol == symbol)
                .where(CatalystSignal.expires_at > now)
                .order_by(CatalystSignal.scraped_at.desc())
                .limit(1)
            )
            result = row.first()
            if result is None:
                _set_cache(symbol, 0.0)
                return 0.0

            boost = float(result.scorer_boost or 0.0)
            _set_cache(symbol, boost)
            return boost

    except Exception as exc:
        logger.debug("[catalyst/boost] DB lookup failed for %s: %s", symbol, exc)
        return 0.0


def invalidate_cache(symbol: str | None = None, keep: set[str] | None = None) -> None:
    """Invalidate the boost cache.

    Pass `symbol` to drop one entry, nothing to drop all, or `keep` (a set of
    symbols) to drop everything *except* those — used by the daemon after a
    scrape cycle so entries the scraper no longer covers go stale instead of
    serving a boost the data no longer supports.
    """
    global _cache
    if keep is not None:
        _cache = {s: e for s, e in _cache.items() if s in keep}
    elif symbol is None:
        _cache = {}
    else:
        _cache.pop(symbol, None)
