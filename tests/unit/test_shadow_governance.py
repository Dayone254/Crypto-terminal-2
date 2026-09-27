"""Unit tests for shadow mode staging and promotion governance boundaries."""
from __future__ import annotations

import sqlite3
import pytest
from tpt.backtest.shadow import (
    list_staged_shadow_pipelines,
    promote_shadow_pipeline_manual,
    stage_candidate_strategy,
)
from tpt.config.settings import settings


def test_shadow_staging_and_promotion_governance():
    """Assert staging works, promotion is rejected if sample < 30, and requires manual action."""
    # Clean up any existing test state
    db_path = settings.sqlite_path
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS shadow_pipelines (pipeline_version TEXT PRIMARY KEY, candidate_name TEXT, staged_at TEXT, sample_count INTEGER, target_sample_size INTEGER, status TEXT, config_json TEXT, promoted_at TEXT)")
        conn.execute("DELETE FROM shadow_pipelines WHERE pipeline_version LIKE 'v3.0-%'")
        conn.execute("CREATE TABLE IF NOT EXISTS signals (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, timestamp INTEGER NOT NULL DEFAULT 0, score REAL NOT NULL DEFAULT 0, label TEXT NOT NULL DEFAULT '', entry_price REAL NOT NULL DEFAULT 0, tp_price REAL NOT NULL DEFAULT 0, sl_price REAL NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'PENDING', trade_direction TEXT DEFAULT 'LONG', scan_run_id INTEGER, pipeline_version TEXT DEFAULT 'v1.0')")
        conn.execute("DELETE FROM signals WHERE pipeline_version LIKE 'v3.0-%'")
        conn.commit()

    # 1. Stage a candidate strategy
    staged = stage_candidate_strategy("Test Candidate Strategy", {"min_score": 60})
    p_ver = staged["pipeline_version"]
    assert p_ver == "v3.0-test-candidate-strategy"
    assert staged["status"] == "STAGED"
    assert staged["eligible_for_promotion"] is False

    # 2. Attempt promotion with 0 samples — MUST raise ValueError (Boundary Safety Property)
    with pytest.raises(ValueError) as exc_info:
        promote_shadow_pipeline_manual(p_ver)
    assert "insufficient shadow sample count" in str(exc_info.value)

    # 3. Simulate 15 closed trades (below threshold of 30) — MUST still raise ValueError
    with sqlite3.connect(db_path) as conn:
        for i in range(15):
            conn.execute(
                """INSERT INTO signals 
                (symbol, timestamp, score, label, entry_price, tp_price, sl_price, status, trade_direction, pipeline_version)
                VALUES ('BTC-USD', 1700000000, 75.0, 'ENTRY_ZONE', 50000, 52000, 49000, 'WIN', 'LONG', ?)""",
                (p_ver,),
            )
        conn.commit()

    pipelines_15 = list_staged_shadow_pipelines()
    matching_15 = [p for p in pipelines_15 if p["pipeline_version"] == p_ver]
    assert len(matching_15) == 1
    assert matching_15[0]["sample_count"] == 15
    assert matching_15[0]["eligible_for_promotion"] is False

    with pytest.raises(ValueError) as exc_info_15:
        promote_shadow_pipeline_manual(p_ver)
    assert "insufficient shadow sample count" in str(exc_info_15.value)

    # 4. Insert 15 more closed shadow trades (total 30 closed trades)
    with sqlite3.connect(db_path) as conn:
        for i in range(15, 30):
            conn.execute(
                """INSERT INTO signals 
                (symbol, timestamp, score, label, entry_price, tp_price, sl_price, status, trade_direction, pipeline_version)
                VALUES ('BTC-USD', 1700000000, 75.0, 'ENTRY_ZONE', 50000, 52000, 49000, 'WIN', 'LONG', ?)""",
                (p_ver,),
            )
        conn.commit()

    # 5. Verify list_staged_shadow_pipelines reflects 30 samples and ELIGIBLE status
    pipelines_30 = list_staged_shadow_pipelines()
    matching_30 = [p for p in pipelines_30 if p["pipeline_version"] == p_ver]
    assert len(matching_30) == 1
    assert matching_30[0]["sample_count"] == 30
    assert matching_30[0]["eligible_for_promotion"] is True

    # 6. Execute explicit manual promotion
    promoted = promote_shadow_pipeline_manual(p_ver)
    assert promoted["status"] == "PROMOTED"
    assert promoted["sample_count"] == 30
