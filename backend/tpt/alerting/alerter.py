"""Alert generation and deduplication engine.

Implements PRD §10: zone-entry detection with ±tolerance, dedupe keys, watch
open/close lifecycle, and quiet-hours suppression.

`generate_alerts()` is pure (no I/O) so it can be unit-tested without a database;
`persist_alerts()` performs the writes.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from tpt.config.strategy import AlertConfig
from tpt.db.models import utcnow_iso

logger = logging.getLogger(__name__)

AlertRecord = dict[str, Any]

# ±0.3% zone entry tolerance (PRD §10); a watch closes once price leaves the zone
# by more than 1.5%.
DEFAULT_ENTRY_TOLERANCE_PCT = 0.3
DEFAULT_EXIT_TOLERANCE_PCT = 1.5

_ZONE_ALERT_TYPES = {"TRANCHE_A": "ZONE_A_ENTRY", "TRANCHE_B": "ZONE_B_ENTRY"}


def build_dedupe_key(symbol: str, alert_type: str, zone_price: float) -> str:
    """Stable key identifying one alert event for a symbol+zone."""
    return f"{symbol}:{alert_type}:{round(float(zone_price), 2)}"


def _within_tolerance(price: float, level: float | None, tolerance_pct: float) -> bool:
    if not level or level <= 0 or not price or price <= 0:
        return False
    return abs(price - level) / level * 100.0 <= tolerance_pct


def _ladder_price(ladder: dict[str, Any] | None, key: str) -> float | None:
    if not ladder:
        return None
    value = ladder.get(key)
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def generate_alerts(
    scan_results: list[dict],
    active_watches: dict[tuple[str, str], dict] | list[dict],
    config: AlertConfig | None = None,
    *,
    now_utc: datetime | None = None,
    recent_dedupe_keys: set[str] | None = None,
    entry_tolerance_pct: float = DEFAULT_ENTRY_TOLERANCE_PCT,
    exit_tolerance_pct: float = DEFAULT_EXIT_TOLERANCE_PCT,
) -> list[AlertRecord]:
    """Generate alert records for the current scan results.

    `active_watches` is keyed by (product_id, zone). `recent_dedupe_keys` holds
    keys already fired inside the dedupe window — those are skipped so the same
    zone does not re-alert until the watch closes and the clock resets.
    """
    cfg = config or AlertConfig()
    dedupe_seen = recent_dedupe_keys or set()

    if isinstance(active_watches, list):
        watch_index: dict[tuple[str, str], dict] = {}
        for entry in active_watches:
            pid = entry.get("product_id")
            zone = entry.get("zone")
            if pid and zone:
                watch_index[(str(pid), str(zone))] = entry
    else:
        watch_index = dict(active_watches)

    from tpt.alerting.quiet_hours import is_quiet_now

    alerts: list[AlertRecord] = []

    for result in scan_results:
        pid = result.get("product_id")
        ladder = result.get("ladder")
        price = result.get("last_price")
        if not pid or not ladder or not price:
            continue

        try:
            price = float(price)
        except (TypeError, ValueError):
            continue

        label = result.get("label")
        score = result.get("composite_score")
        direction = result.get("trade_direction", "LONG")
        stop_price = _ladder_price(ladder, "stop_price")

        suppressed = False
        if now_utc is not None:
            suppressed = is_quiet_now(now_utc, cfg.quiet_hours_start, cfg.quiet_hours_end, cfg.timezone)

        # ── Invalidation takes precedence over zone entries ────────────────
        invalidated = False
        if stop_price:
            invalidated = price <= stop_price if direction == "LONG" else price >= stop_price
        if invalidated:
            for zone in ("TRANCHE_A", "TRANCHE_B"):
                if (pid, zone) in watch_index:
                    alerts.append({
                        "product_id": pid,
                        "alert_type": "INVALIDATION",
                        "price_at_alert": price,
                        "zone": zone,
                        "zone_price": stop_price,
                        "zone_tolerance_pct": exit_tolerance_pct,
                        "label_at_alert": label,
                        "score_at_alert": score,
                        "ladder_snapshot": json.dumps(ladder),
                        "dedupe_key": build_dedupe_key(pid, f"INVALIDATION:{zone}", stop_price or 0.0),
                        "suppressed": int(suppressed),
                        "watch_action": "CLOSE",
                        "close_reason": "INVALIDATION",
                    })
            continue

        # ── Zone entry / exit per tranche ──────────────────────────────────
        for zone, price_key in (("TRANCHE_A", "tranche_a_price"), ("TRANCHE_B", "tranche_b_price")):
            level = _ladder_price(ladder, price_key)
            if not level:
                continue

            alert_type = _ZONE_ALERT_TYPES[zone]
            in_zone = _within_tolerance(price, level, entry_tolerance_pct)
            watch = watch_index.get((pid, zone))

            if in_zone and watch is None:
                key = build_dedupe_key(pid, alert_type, level)
                if key in dedupe_seen:
                    continue
                alerts.append({
                    "product_id": pid,
                    "alert_type": alert_type,
                    "price_at_alert": price,
                    "zone": zone,
                    "zone_price": level,
                    "zone_tolerance_pct": entry_tolerance_pct,
                    "label_at_alert": label,
                    "score_at_alert": score,
                    "ladder_snapshot": json.dumps(ladder),
                    "dedupe_key": key,
                    "suppressed": int(suppressed),
                    "watch_action": "OPEN",
                    "entry_price": price,
                })
            elif watch is not None and not in_zone:
                # Close only once price has genuinely left the zone.
                if not _within_tolerance(price, level, exit_tolerance_pct):
                    alerts.append({
                        "product_id": pid,
                        "alert_type": alert_type,
                        "price_at_alert": price,
                        "zone": zone,
                        "zone_price": level,
                        "zone_tolerance_pct": exit_tolerance_pct,
                        "label_at_alert": label,
                        "score_at_alert": score,
                        "ladder_snapshot": json.dumps(ladder),
                        "dedupe_key": build_dedupe_key(pid, f"{alert_type}:EXIT", level),
                        "suppressed": 1,
                        "watch_action": "CLOSE",
                        "close_reason": "PRICE_EXIT",
                    })

    return alerts


async def persist_alerts(db, alerts: list[AlertRecord], scan_run_id: str | None = None) -> int:
    """Apply watch open/close actions and insert Alert rows. Returns rows written."""
    from sqlalchemy import select

    from tpt.db.models import Alert, Watch

    written = 0
    now = utcnow_iso()

    for record in alerts:
        action = record.get("watch_action")
        pid = record["product_id"]
        zone = record.get("zone")

        watch_id: str | None = None

        if action == "OPEN" and zone:
            existing = await db.execute(
                select(Watch).where(
                    Watch.product_id == pid, Watch.zone == zone, Watch.is_active == 1
                )
            )
            watch = existing.scalars().first()
            if watch is None:
                watch = Watch(
                    product_id=pid,
                    zone=zone,
                    zone_price=record["zone_price"],
                    entry_price=record.get("entry_price") or record["price_at_alert"],
                    is_active=1,
                )
                db.add(watch)
                await db.flush()
            watch_id = watch.id

        elif action == "CLOSE" and zone:
            existing = await db.execute(
                select(Watch).where(
                    Watch.product_id == pid, Watch.zone == zone, Watch.is_active == 1
                )
            )
            watch = existing.scalars().first()
            if watch is not None:
                watch.is_active = 0
                watch.closed_at = now
                watch.exit_price = record["price_at_alert"]
                watch.close_reason = record.get("close_reason", "PRICE_EXIT")
                watch_id = watch.id

        db.add(Alert(
            product_id=pid,
            scan_run_id=scan_run_id,
            watch_id=watch_id,
            alert_type=record["alert_type"],
            price_at_alert=record["price_at_alert"],
            zone_price=record.get("zone_price"),
            zone_tolerance_pct=record.get("zone_tolerance_pct"),
            label_at_alert=record.get("label_at_alert"),
            score_at_alert=record.get("score_at_alert"),
            ladder_snapshot=record.get("ladder_snapshot"),
            dedupe_key=record["dedupe_key"],
            suppressed=int(record.get("suppressed", 0)),
        ))
        written += 1

    return written
