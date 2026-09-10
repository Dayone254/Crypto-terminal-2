"""Alert delivery worker — quiet hours + morning digest."""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from sqlalchemy import select

from tpt.alerting.quiet_hours import should_deliver
from tpt.config.strategy import load_strategy
from tpt.db.connection import AsyncSessionLocal
from tpt.db.models import Alert, utcnow_iso
from tpt.db.write_lock import db_write_lock

logger = logging.getLogger(__name__)


async def deliver_pending_alerts() -> int:
    """Mark deliverable pending alerts as delivered.

    Quiet hours gate delivery: during the window nothing is marked delivered, and
    the alerts stay pending for the morning digest. Returns the number delivered.
    """
    cfg = load_strategy().alerts
    now = datetime.now(UTC)

    if not should_deliver(None, now, cfg.quiet_hours_start, cfg.quiet_hours_end, cfg.timezone):
        return 0

    delivered = 0
    async with db_write_lock, AsyncSessionLocal() as db:
        result = await db.execute(
            select(Alert).where(
                Alert.delivered_at.is_(None),
                Alert.suppressed == 0,
                Alert.alert_type != "DIGEST",
            )
        )
        rows = result.scalars().all()
        if rows:
            stamp = utcnow_iso()
            for alert in rows:
                alert.delivered_at = stamp
            await db.commit()
            delivered = len(rows)

    if delivered:
        logger.info("Delivered %d alert(s).", delivered)
    return delivered


async def deliver_morning_digest() -> int:
    """Bundle quiet-hours-suppressed alerts into DIGEST alerts and deliver them.

    Called after the quiet window ends (default 08:00 Nairobi). One DIGEST row is
    created per symbol; the underlying alerts are marked delivered. Returns the
    number of alerts folded into digests.
    """
    cfg = load_strategy().alerts
    now = datetime.now(UTC)

    # Only run once the quiet window has passed.
    if not should_deliver(None, now, cfg.quiet_hours_start, cfg.quiet_hours_end, cfg.timezone):
        return 0

    folded = 0
    async with db_write_lock, AsyncSessionLocal() as db:
        result = await db.execute(
            select(Alert).where(
                Alert.delivered_at.is_(None),
                Alert.suppressed == 1,
                Alert.alert_type != "DIGEST",
            )
        )
        rows = result.scalars().all()
        if not rows:
            return 0

        stamp = utcnow_iso()
        by_symbol: dict[str, list[Alert]] = {}
        for alert in rows:
            by_symbol.setdefault(alert.product_id, []).append(alert)

        for symbol, group in by_symbol.items():
            summary = [
                {
                    "alert_type": a.alert_type,
                    "price_at_alert": a.price_at_alert,
                    "zone_price": a.zone_price,
                    "label_at_alert": a.label_at_alert,
                    "score_at_alert": a.score_at_alert,
                    "created_at": a.created_at,
                }
                for a in group
            ]
            db.add(Alert(
                product_id=symbol,
                alert_type="DIGEST",
                price_at_alert=group[-1].price_at_alert,
                label_at_alert=group[-1].label_at_alert,
                score_at_alert=group[-1].score_at_alert,
                ladder_snapshot=json.dumps(summary),
                dedupe_key=f"{symbol}:DIGEST:{stamp[:13]}",
                delivered_at=stamp,
            ))
            for alert in group:
                alert.delivered_at = stamp
            folded += len(group)

        await db.commit()

    if folded:
        logger.info("Folded %d suppressed alert(s) into morning digests.", folded)
    return folded
