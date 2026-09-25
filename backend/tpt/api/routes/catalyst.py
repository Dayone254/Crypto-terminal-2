"""Catalyst Intelligence API routes.

GET  /api/v1/catalyst/feed    — ranked list of active catalyst signals
POST /api/v1/catalyst/refresh — trigger a fresh scrape cycle (on-demand)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Query

from tpt.db.connection import AsyncSessionLocal
from tpt.db.models import CatalystSignal

router = APIRouter()
logger = logging.getLogger(__name__)

_TIER_ORDER = {"CRITICAL": 0, "HIGH": 1, "WATCH": 2, "NOISE": 3}
_MIN_TIER_DEFAULT = "HIGH"


def _serialize(row: CatalystSignal) -> dict[str, Any]:
    return {
        "symbol": row.symbol,
        "coin_id": row.coin_id,
        "catalyst_score": row.catalyst_score,
        "priority_tier": row.priority_tier,
        "volume_surge_ratio": row.volume_surge_ratio,
        "volume_surge_score": row.volume_surge_score,
        "dev_activity_score": row.dev_activity_score,
        "news_score": row.news_score,
        "github_stars_score": row.github_stars_score,
        "commit_count_4w": row.commit_count_4w,
        "pr_merged_4w": row.pr_merged_4w,
        "github_stars": row.github_stars,
        "top_headline": row.top_headline,
        "catalyst_keywords": row.catalyst_keywords.split(",") if row.catalyst_keywords else [],
        "scorer_boost": row.scorer_boost,
        "scraped_at": row.scraped_at.isoformat() if row.scraped_at else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
    }


@router.get("/feed")
async def catalyst_feed(
    min_tier: str = Query(default=_MIN_TIER_DEFAULT, description="Minimum priority tier: CRITICAL, HIGH, WATCH, NOISE"),
    limit: int = Query(default=30, ge=1, le=200),
):
    """Return the current ranked catalyst signal feed.

    Signals are sorted CRITICAL → HIGH → WATCH → NOISE, then by descending
    catalyst_score within each tier.  Only unexpired signals (expires_at > now) are returned.
    """
    from sqlalchemy import select

    min_tier = min_tier.upper()
    if min_tier not in _TIER_ORDER:
        min_tier = _MIN_TIER_DEFAULT

    allowed_tiers = [t for t, rank in _TIER_ORDER.items() if rank <= _TIER_ORDER[min_tier]]
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        rows_result = await db.execute(
            select(CatalystSignal)
            .where(
                CatalystSignal.priority_tier.in_(allowed_tiers),
                CatalystSignal.expires_at > now,
            )
            .order_by(CatalystSignal.catalyst_score.desc())
            .limit(limit * 3)  # over-fetch before dedup
        )
        rows = rows_result.scalars().all()

    # Dedup: keep highest-scored row per symbol
    seen_symbols: set[str] = set()
    deduped: list[CatalystSignal] = []
    for row in rows:
        if row.symbol not in seen_symbols:
            deduped.append(row)
            seen_symbols.add(row.symbol)
        if len(deduped) >= limit:
            break

    # Sort by tier then score
    deduped.sort(key=lambda r: (_TIER_ORDER.get(r.priority_tier, 99), -r.catalyst_score))

    return {
        "generated_at": now.isoformat(),
        "total_signals": len(deduped),
        "min_tier_filter": min_tier,
        "signals": [_serialize(r) for r in deduped],
    }


@router.post("/refresh")
async def catalyst_refresh(background_tasks: BackgroundTasks):
    """Trigger an immediate catalyst scrape cycle.

    Runs in the background so the response returns instantly.
    """
    from tpt.catalyst.daemon import run_once

    background_tasks.add_task(run_once)
    return {
        "status": "QUEUED",
        "message": "Catalyst scrape cycle triggered in background.",
    }
