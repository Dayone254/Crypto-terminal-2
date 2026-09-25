"""Catalyst daemon — background async loop that runs the scraper + analyzer
and persists results to the `catalyst_signals` table.

Lifecycle:
  - Runs every `settings.catalyst_scrape_interval_seconds` (default 900s / 15 min)
  - On each cycle:
      1. Collects active symbols from watchlist + last scan top-50
      2. Fetches catalyst data (CoinGecko + CryptoCompare) in batches of 10
      3. Scores each symbol via the analyzer
      4. Upserts the result into `catalyst_signals`
      5. Invalidates the watchlist_boost cache so scorer picks up new data
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from tpt.catalyst import analyzer, scraper
from tpt.catalyst.watchlist_boost import invalidate_cache
from tpt.config.settings import settings

if TYPE_CHECKING:
    from tpt.catalyst.analyzer import CatalystScore

logger = logging.getLogger(__name__)

_BATCH_SIZE = 10  # symbols per scraper batch (respects free-tier rate limits)


async def _get_target_symbols() -> list[str]:
    """Collect symbols to scrape.

    Priority order:
      1. Watchlist symbols (Symbol.on_watchlist == 1)
      2. Top-M symbols from the most recent completed scan (by composite score)
    Capped at `settings.catalyst_max_symbols`.
    """
    from tpt.db.connection import AsyncSessionLocal
    from tpt.db.models import Score, Symbol

    symbols: list[str] = []
    seen: set[str] = set()

    try:
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select

            # 1. Watchlist symbols
            rows = await db.execute(
                select(Symbol.product_id).where(Symbol.on_watchlist == 1, Symbol.active == 1)
            )
            for (sym,) in rows:
                if sym not in seen:
                    symbols.append(sym)
                    seen.add(sym)

            # 2. Latest scan top signals ranked by composite score
            cap = settings.catalyst_max_symbols - len(symbols)
            if cap > 0:
                sub = (
                    select(Score.product_id, Score.composite_score)
                    .order_by(Score.composite_score.desc())
                    .limit(cap)
                )
                rows2 = await db.execute(sub)
                for product_id, _ in rows2:
                    if product_id not in seen:
                        symbols.append(product_id)
                        seen.add(product_id)

    except Exception as exc:
        logger.warning("[catalyst_daemon] Failed to get target symbols: %s", exc)

    # Fallback: always include the major pairs
    majors = ["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "LINK-USD",
               "OP-USD", "ARB-USD", "MATIC-USD", "NEAR-USD", "INJ-USD"]
    for sym in majors:
        if sym not in seen and len(symbols) < settings.catalyst_max_symbols:
            symbols.append(sym)

    return symbols[:settings.catalyst_max_symbols]


async def _load_avg_volumes() -> dict[str, float]:
    """Load 7-day average volumes from stored catalyst history.

    Averages the last 7 scraped `volume_24h` records per symbol.
    Returns an empty dict if the table is too young.
    """
    avg: dict[str, float] = {}
    try:
        from tpt.db.connection import AsyncSessionLocal
        from tpt.db.models import CatalystSignal
        from sqlalchemy import select, func

        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                select(CatalystSignal.symbol, func.avg(CatalystSignal.volume_24h))
                .where(CatalystSignal.scraped_at > cutoff)
                .group_by(CatalystSignal.symbol)
            )
            for sym, avg_vol in rows:
                if avg_vol:
                    avg[sym] = float(avg_vol)
    except Exception as exc:
        logger.debug("[catalyst_daemon] avg_volume load failed: %s", exc)
    return avg


async def _upsert_signal(cs: "CatalystScore") -> None:
    """Insert or replace the latest catalyst signal for a symbol."""
    from tpt.db.connection import AsyncSessionLocal
    from tpt.db.models import CatalystSignal
    from sqlalchemy import select

    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=24)

    async with AsyncSessionLocal() as db:
        try:
            # Soft upsert: insert a new row (history preserved for avg_volume calc)
            signal = CatalystSignal(
                symbol=cs.symbol,
                coin_id=cs.coin_id,
                catalyst_score=cs.catalyst_score,
                priority_tier=cs.priority_tier,
                volume_surge_score=cs.volume_surge_score,
                dev_activity_score=cs.dev_activity_score,
                news_score=cs.news_score,
                github_stars_score=cs.github_stars_score,
                volume_surge_ratio=cs.volume_surge_ratio,
                volume_24h=0.0,  # populated below
                commit_count_4w=cs.commit_count_4w,
                pr_merged_4w=cs.pr_merged_4w,
                github_stars=cs.github_stars,
                top_headline=cs.top_headline,
                catalyst_keywords=",".join(cs.catalyst_keywords_found),
                scorer_boost=cs.scorer_boost,
                scraped_at=now,
                expires_at=expires,
            )
            db.add(signal)
            await db.commit()
        except Exception as exc:
            logger.warning("[catalyst_daemon] DB upsert failed for %s: %s", cs.symbol, exc)
            await db.rollback()


def _batched(lst: list, n: int):
    for i in range(0, len(lst), n):
        yield lst[i: i + n]


async def run_once() -> dict[str, int]:
    """Run a single catalyst scrape + score + persist cycle.

    Returns a summary dict with counts by tier.
    """
    symbols = await _get_target_symbols()
    avg_volumes = await _load_avg_volumes()

    tier_counts: dict[str, int] = {"CRITICAL": 0, "HIGH": 0, "WATCH": 0, "NOISE": 0}
    total_scraped = 0

    for batch in _batched(symbols, _BATCH_SIZE):
        try:
            raw_list = await scraper.fetch_batch(batch, avg_volumes=avg_volumes)
            for raw in raw_list:
                if raw.error:
                    continue
                cs = analyzer.score(raw)
                await _upsert_signal(cs)
                tier_counts[cs.priority_tier] = tier_counts.get(cs.priority_tier, 0) + 1
                total_scraped += 1
            # Respect free-tier: pause between batches
            await asyncio.sleep(1.5)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("[catalyst_daemon] Batch error (%s): %s", batch, exc)

    # Invalidate watchlist_boost cache so the scorer gets fresh data
    invalidate_cache()

    logger.info(
        "[catalyst_daemon] Scraped %d symbols — CRITICAL:%d HIGH:%d WATCH:%d NOISE:%d",
        total_scraped,
        tier_counts.get("CRITICAL", 0),
        tier_counts.get("HIGH", 0),
        tier_counts.get("WATCH", 0),
        tier_counts.get("NOISE", 0),
    )
    return tier_counts


async def catalyst_daemon_loop() -> None:
    """Infinite background loop registered in main.py lifespan."""
    interval = settings.catalyst_scrape_interval_seconds
    if interval <= 0:
        logger.info("[catalyst_daemon] Disabled (catalyst_scrape_interval_seconds=%s).", interval)
        return

    logger.info("[catalyst_daemon] Starting — interval=%ss, max_symbols=%s",
                interval, settings.catalyst_max_symbols)

    # Yield 15s on startup so FastAPI web server starts instantly and serves API requests without delay
    await asyncio.sleep(15.0)
    try:
        await run_once()
    except Exception as exc:
        logger.error("[catalyst_daemon] Startup run failed: %s", exc)


    while True:
        await asyncio.sleep(interval)
        try:
            await run_once()
        except asyncio.CancelledError:
            logger.info("[catalyst_daemon] Shutting down.")
            raise
        except Exception as exc:
            logger.error("[catalyst_daemon] Cycle error: %s", exc)
