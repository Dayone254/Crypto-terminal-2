"""Health check routes."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    """Liveness check."""
    return {"status": "ok", "version": "0.1.0"}


@router.get("/health/db")
async def health_db() -> dict:
    """Database connectivity check. TODO (M0): verify DB connection."""
    return {"status": "ok", "db": "not_checked"}
