"""Health check routes."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    """Liveness check."""
    return {"status": "ok", "version": "0.1.0"}


@router.get("/health/db")
async def health_db() -> dict:
    """Database connectivity check."""
    from sqlalchemy import text
    from tpt.db.connection import AsyncSessionLocal
    import logging
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        return {"status": "ok", "db": "connected"}
    except Exception as exc:
        logging.getLogger(__name__).error(f"DB health check failed: {exc}")
        return {"status": "error", "db": "disconnected"}
