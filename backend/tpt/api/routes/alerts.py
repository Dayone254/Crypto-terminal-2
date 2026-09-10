"""Alert routes — recent alerts, pending (quiet-hours) alerts, and dismissal."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from tpt.db.connection import AsyncSessionLocal
from tpt.db.write_lock import db_write_lock

router = APIRouter()


@router.get("")
async def list_alerts(page: int = 1, per_page: int = 20) -> list:
    """Return recent alerts, newest first, paginated."""
    from sqlalchemy import select

    from tpt.db.models import Alert

    page = max(1, page)
    per_page = max(1, min(per_page, 200))

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Alert)
            .order_by(Alert.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        return [
            {
                "id": a.id,
                "product_id": a.product_id,
                "alert_type": a.alert_type,
                "price_at_alert": a.price_at_alert,
                "zone_price": a.zone_price,
                "label_at_alert": a.label_at_alert,
                "score_at_alert": a.score_at_alert,
                "created_at": a.created_at,
                "delivered_at": a.delivered_at,
                "suppressed": bool(a.suppressed),
                "dismissed_by_user": bool(a.dismissed_by_user),
            }
            for a in result.scalars().all()
        ]


@router.get("/pending")
async def pending_alerts() -> list:
    """Return undelivered (quiet-hours suppressed) alerts."""
    from sqlalchemy import select

    from tpt.db.models import Alert

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Alert)
            .where(Alert.delivered_at.is_(None), Alert.dismissed_by_user == 0)
            .order_by(Alert.created_at.desc())
            .limit(200)
        )
        return [
            {
                "id": a.id,
                "product_id": a.product_id,
                "alert_type": a.alert_type,
                "price_at_alert": a.price_at_alert,
                "zone_price": a.zone_price,
                "label_at_alert": a.label_at_alert,
                "score_at_alert": a.score_at_alert,
                "created_at": a.created_at,
                "suppressed": bool(a.suppressed),
            }
            for a in result.scalars().all()
        ]


@router.patch("/{alert_id}/dismiss")
async def dismiss_alert(alert_id: str) -> dict:
    """Mark an alert as dismissed by the user."""
    from tpt.db.models import Alert

    async with db_write_lock, AsyncSessionLocal() as db:
        alert = await db.get(Alert, alert_id)
        if alert is None:
            raise HTTPException(status_code=404, detail=f"Alert '{alert_id}' not found.")
        alert.dismissed_by_user = 1
        await db.commit()

    return {"alert_id": alert_id, "dismissed": True}
