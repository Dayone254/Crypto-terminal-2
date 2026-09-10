"""Scan trigger and status routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks
from sqlalchemy import select

from tpt.db.connection import AsyncSessionLocal
from tpt.db.models import ScanRun
from tpt.scanner.runner import is_scan_running, run_scan

router = APIRouter()


@router.post("/start", response_model=dict[str, Any])
async def trigger_scan(background_tasks: BackgroundTasks) -> dict[str, Any]:
    """Trigger an on-demand market scan in the background."""
    if is_scan_running():
        # Refuse to stack a second scan: concurrent scans double upstream API
        # load and contend for SQLite's single write lock.
        return {
            "status": "ALREADY_RUNNING",
            "message": "A scan is already in progress.",
        }

    background_tasks.add_task(run_scan, trigger="ON_DEMAND")
    return {"status": "QUEUED", "message": "On-demand scan triggered."}


@router.get("/status", response_model=dict[str, Any])
async def get_scan_status() -> dict[str, Any]:
    """Return the status of the latest scan run."""
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(ScanRun).order_by(ScanRun.started_at.desc()).limit(1))
        latest = res.scalar_one_or_none()
        if latest is None:
            return {"status": "IDLE", "latest_scan": None, "in_progress": is_scan_running()}
        return {
            "status": latest.status,
            "in_progress": is_scan_running(),
            "scan_run_id": latest.id,
            "trigger": latest.trigger,
            "started_at": latest.started_at,
            "completed_at": latest.completed_at,
            "duration_seconds": latest.duration_seconds,
            "symbols_fetched": latest.symbols_fetched,
            "symbols_stale": latest.symbols_stale,
            "candidates_count": latest.candidates_count,
            "error_message": latest.error_message,
        }
