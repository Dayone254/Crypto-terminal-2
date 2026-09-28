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


def _extract_levels(ladder_snapshot: str | None) -> tuple[float | None, float | None]:
    """Real TP/SL for an alert, parsed from its ladder snapshot.

    Zone-entry and invalidation alerts store the full ladder dict computed at
    alert time (keys ``target_1_price`` / ``stop_price``). Snapshots without
    those keys — DIGEST previews, malformed or absent JSON — yield ``(None,
    None)`` so the message ships without levels instead of fabricated ones.
    """
    if not ladder_snapshot:
        return None, None
    try:
        snap = json.loads(ladder_snapshot)
    except (TypeError, ValueError):
        return None, None
    if not isinstance(snap, dict):
        return None, None
    try:
        tp = float(snap["target_1_price"]) if snap.get("target_1_price") is not None else None
        sl = float(snap["stop_price"]) if snap.get("stop_price") is not None else None
    except (TypeError, ValueError):
        return None, None
    if tp is not None and tp <= 0:
        tp = None
    if sl is not None and sl <= 0:
        sl = None
    return tp, sl


async def deliver_pending_alerts() -> int:
    """Deliver pending (unsuppressed) alerts to Telegram.

    Three rules keep this correct and cheap:

    1. TP/SL come from the alert's ladder snapshot — the real levels the ladder
       computed at alert time. Snapshots that lack them ship a message without
       TP/SL instead of the fabricated +5%/-3% numbers this used to invent.
    2. The SQLite write lock is never held across network I/O: candidates are
       read under one short lock, Telegram is called with no lock and no open
       session, and only successful sends are re-stamped under a fresh one.
    3. A failed send is NOT marked delivered — the alert stays pending and is
       retried on the next cycle instead of being silently lost forever.

    Quiet hours gate delivery: during the window nothing is sent, and the
    alerts stay pending for the morning digest. Returns the number delivered.
    """
    cfg = load_strategy().alerts
    now = datetime.now(UTC)

    if not should_deliver(None, now, cfg.quiet_hours_start, cfg.quiet_hours_end, cfg.timezone):
        return 0

    # Read candidates under a short lock, then release it before any network I/O.
    async with db_write_lock, AsyncSessionLocal() as db:
        result = await db.execute(
            select(
                Alert.id,
                Alert.product_id,
                Alert.score_at_alert,
                Alert.label_at_alert,
                Alert.price_at_alert,
                Alert.ladder_snapshot,
            ).where(
                Alert.delivered_at.is_(None),
                Alert.suppressed == 0,
                Alert.alert_type != "DIGEST",
            )
        )
        rows = result.all()

    if not rows:
        return 0

    # Telegram I/O runs OUTSIDE db_write_lock and with no open DB session —
    # holding the SQLite write lock across HTTP stalled every reader and writer
    # for the duration of each send.
    sent_ids: list[str] = []
    for row in rows:
        tp, sl = _extract_levels(row.ladder_snapshot)
        try:
            from tpt.alerts.telegram import send_setup_alert
            await send_setup_alert(
                symbol=row.product_id,
                score=row.score_at_alert or 0.0,
                label=row.label_at_alert or "WATCH",
                entry=float(row.price_at_alert or 0.0),
                tp=tp,
                sl=sl,
                bypass_quiet_hours=True,
            )
            sent_ids.append(row.id)
        except Exception as exc:
            logger.warning(
                "Telegram delivery failed for alert %s (%s): %s", row.id, row.product_id, exc
            )

    # Stamp only the alerts that actually sent, under a fresh short lock. Failed
    # rows keep delivered_at NULL so the next cycle retries them. The is_(None)
    # guard also keeps a concurrent worker from double-stamping.
    delivered = 0
    if sent_ids:
        async with db_write_lock, AsyncSessionLocal() as db:
            result = await db.execute(
                select(Alert).where(Alert.id.in_(sent_ids), Alert.delivered_at.is_(None))
            )
            stamp = utcnow_iso()
            for alert in result.scalars().all():
                alert.delivered_at = stamp
                delivered += 1
            await db.commit()

    if rows:
        logger.info("Alert delivery: %d/%d sent.", delivered, len(rows))
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
