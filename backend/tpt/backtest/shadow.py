"""Shadow-mode staging and promotion governance manager.

NON-NEGOTIABLE: No strategy candidate is ever auto-promoted to live trading.
Promotion requires an explicit human action.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

from tpt.config.settings import settings
from tpt.db.models import new_uuid, utcnow_iso

logger = logging.getLogger(__name__)


def ensure_shadow_tables() -> None:
    """Ensure shadow_pipelines table exists."""
    db_path = settings.sqlite_path
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS shadow_pipelines (
                pipeline_version TEXT PRIMARY KEY,
                candidate_name TEXT NOT NULL,
                staged_at TEXT NOT NULL,
                sample_count INTEGER NOT NULL DEFAULT 0,
                target_sample_size INTEGER NOT NULL DEFAULT 30,
                status TEXT NOT NULL DEFAULT 'STAGED',
                config_json TEXT NOT NULL,
                promoted_at TEXT
            )"""
        )
        conn.commit()


def stage_candidate_strategy(
    candidate_name: str,
    config_dict: dict[str, Any],
    version_suffix: str = "staged",
) -> dict[str, Any]:
    """Stage a strategy candidate to run forward in shadow mode."""
    ensure_shadow_tables()
    db_path = settings.sqlite_path

    # Generate pipeline version identifier, e.g. v3.0-aggressive-score-gte-55
    if version_suffix == "staged" and candidate_name:
        clean_slug = (
            candidate_name.lower()
            .replace(" ", "-")
            .replace("(", "")
            .replace(")", "")
            .replace(">=", "gte")
            .replace("=", "")
        )
        version_suffix = clean_slug

    pipeline_version = f"v3.0-{version_suffix}"
    staged_at = utcnow_iso()
    target_sample_size = settings.min_shadow_sample_size

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO shadow_pipelines 
            (pipeline_version, candidate_name, staged_at, sample_count, target_sample_size, status, config_json)
            VALUES (?, ?, ?, 0, ?, 'STAGED', ?)""",
            (pipeline_version, candidate_name, staged_at, target_sample_size, json.dumps(config_dict)),
        )
        conn.commit()

    logger.info("Staged candidate strategy '%s' as pipeline version %s", candidate_name, pipeline_version)
    return {
        "pipeline_version": pipeline_version,
        "candidate_name": candidate_name,
        "staged_at": staged_at,
        "sample_count": 0,
        "target_sample_size": target_sample_size,
        "status": "STAGED",
        "eligible_for_promotion": False,
    }


def list_staged_shadow_pipelines() -> list[dict[str, Any]]:
    """Retrieve all shadow pipeline versions and their live sample count vs threshold."""
    ensure_shadow_tables()
    db_path = settings.sqlite_path

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT pipeline_version, candidate_name, staged_at, target_sample_size, status, config_json, promoted_at FROM shadow_pipelines")
        rows = cursor.fetchall()

        pipelines = []
        for r in rows:
            p_ver = r[0]
            cand_name = r[1]
            staged_at = r[2]
            target_sample = r[3]
            status = r[4]
            config_json = r[5]
            promoted_at = r[6]

            # Count closed shadow trades matching this pipeline version
            cursor.execute(
                """SELECT COUNT(*) FROM signals 
                WHERE pipeline_version = ? AND status IN ('WIN', 'LOSS', 'BREAK_EVEN', 'PARTIAL_WIN')""",
                (p_ver,),
            )
            closed_cnt = cursor.fetchone()[0]

            # Calculate win rate for shadow cohort
            cursor.execute(
                """SELECT 
                    SUM(CASE WHEN status IN ('WIN', 'PARTIAL_WIN') THEN 1 ELSE 0 END) as wins,
                    COUNT(*) as total
                FROM signals
                WHERE pipeline_version = ? AND status IN ('WIN', 'LOSS', 'BREAK_EVEN', 'PARTIAL_WIN')""",
                (p_ver,),
            )
            stats = cursor.fetchone()
            wins = stats[0] or 0
            tot = stats[1] or 0
            win_rate = round(wins / tot * 100.0, 1) if tot > 0 else 0.0

            eligible = closed_cnt >= target_sample and status == "STAGED"
            if eligible:
                status = "ELIGIBLE"

            pipelines.append({
                "pipeline_version": p_ver,
                "candidate_name": cand_name,
                "staged_at": staged_at,
                "sample_count": closed_cnt,
                "target_sample_size": target_sample,
                "status": status,
                "eligible_for_promotion": eligible,
                "win_rate": win_rate,
                "promoted_at": promoted_at,
                "config": json.loads(config_json) if config_json else {},
            })

        return pipelines


def promote_shadow_pipeline_manual(pipeline_version: str) -> dict[str, Any]:
    """Manually promote a staged shadow pipeline to live trading.
    
    NON-NEGOTIABLE: MUST be triggered by an explicit human action.
    """
    ensure_shadow_tables()
    db_path = settings.sqlite_path

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT candidate_name, target_sample_size, status FROM shadow_pipelines WHERE pipeline_version = ?", (pipeline_version,))
        row = cursor.fetchone()

        if not row:
            raise ValueError(f"Shadow pipeline version '{pipeline_version}' not found.")

        cand_name, target_sample, curr_status = row

        # Count closed shadow sample
        cursor.execute(
            "SELECT COUNT(*) FROM signals WHERE pipeline_version = ? AND status IN ('WIN', 'LOSS', 'BREAK_EVEN', 'PARTIAL_WIN')",
            (pipeline_version,),
        )
        sample_count = cursor.fetchone()[0]

        if sample_count < target_sample:
            raise ValueError(
                f"Cannot promote '{pipeline_version}': insufficient shadow sample count ({sample_count}/{target_sample})."
            )

        now_iso = utcnow_iso()
        cursor.execute(
            "UPDATE shadow_pipelines SET status = 'PROMOTED', promoted_at = ? WHERE pipeline_version = ?",
            (now_iso, pipeline_version),
        )
        conn.commit()

        logger.info("Human operator manually promoted shadow pipeline %s to live capital.", pipeline_version)

        return {
            "pipeline_version": pipeline_version,
            "candidate_name": cand_name,
            "status": "PROMOTED",
            "promoted_at": now_iso,
            "sample_count": sample_count,
            "message": f"Successfully promoted {pipeline_version} to live status.",
        }
