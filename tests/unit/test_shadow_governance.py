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
        conn.execute("DELETE FROM shadow_pipelines WHERE pipeline_version = 'v3.0-staged'")
        conn.execute("CREATE TABLE IF NOT EXISTS signals (id TEXT PRIMARY KEY, scan_run_id TEXT, product_id TEXT, composite_score REAL, score_breakdown TEXT, label TEXT, trade_direction TEXT, tranche_a_price REAL, target_1_price REAL, target_2_price REAL, stop_price REAL, status TEXT, pipeline_version TEXT)")
        conn.execute("DELETE FROM signals WHERE pipeline_version = 'v3.0-staged'")
        conn.commit()

    # 1. Stage a candidate strategy
    staged = stage_candidate_strategy("Test Candidate Strategy", {"min_score": 60})
    p_ver = staged["pipeline_version"]
    assert p_ver == "v3.0-staged"
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
                """INSERT OR REPLACE INTO signals 
                (id, scan_run_id, product_id, composite_score, score_breakdown, label, trade_direction, tranche_a_price, target_1_price, target_2_price, stop_price, status, pipeline_version)
                VALUES (?, 'test_run', 'BTC-USD', 75.0, '{}', 'ENTRY_ZONE', 'LONG', 50000, 52000, 53000, 49000, 'WIN', ?)""",
                (f"sig_{i}", p_ver),
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
                """INSERT OR REPLACE INTO signals 
                (id, scan_run_id, product_id, composite_score, score_breakdown, label, trade_direction, tranche_a_price, target_1_price, target_2_price, stop_price, status, pipeline_version)
                VALUES (?, 'test_run', 'BTC-USD', 75.0, '{}', 'ENTRY_ZONE', 'LONG', 50000, 52000, 53000, 49000, 'WIN', ?)""",
                (f"sig_{i}", p_ver),
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
