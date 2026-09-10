"""Alert routes."""
from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def list_alerts(page: int = 1, per_page: int = 20) -> list:
    """Return recent alerts, paginated. TODO (M3/M4)."""
    return []


@router.get("/pending")
async def pending_alerts() -> list:
    """Return undelivered (quiet-hours suppressed) alerts. TODO (M3)."""
    return []


@router.patch("/{alert_id}/dismiss")
async def dismiss_alert(alert_id: str) -> dict:
    """Mark alert as dismissed by user. TODO (M3/M4)."""
    return {"alert_id": alert_id, "dismissed": True}
