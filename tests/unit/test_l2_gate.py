"""Unit tests for the deterministic L2 confirmation gate and fail-closed signal filtering."""
from __future__ import annotations

import pytest
from tpt.engine.ladder import confirm_l2_structure


def test_confirm_l2_structure_no_data():
    """Fail-closed: Returns fail when no L2 orderbook data is provided."""
    res = confirm_l2_structure("BTC-USD", "LONG", 50000.0, l2_bids=None)
    assert res["passed"] is False
    assert res["reason"] == "NO_L2_BID_DATA"


def test_confirm_l2_structure_long_pass():
    """Returns pass when a bid wall >= $50k USD exists within 2% of entry price."""
    # Entry at 50,000. Bid wall at 49,500 (1% below) with 2 BTC volume ($99,000 USD)
    l2_bids = [
        [49500.0, 2.0],
        [49000.0, 1.0],
    ]
    res = confirm_l2_structure("BTC-USD", "LONG", 50000.0, l2_bids=l2_bids, min_wall_usd=50000.0)
    assert res["passed"] is True
    assert res["wall_price"] == 49500.0
    assert res["l2_volume_usd"] == 99000.0


def test_confirm_l2_structure_long_fail_thin_depth():
    """REJECTS setup when orderbook bid wall volume is thin (< $50k USD threshold)."""
    # Entry at 50,000. Bid wall at 49,500 has only 0.2 BTC ($9,900 USD)
    l2_bids = [
        [49500.0, 0.2],
        [49000.0, 0.1],
    ]
    res = confirm_l2_structure("BTC-USD", "LONG", 50000.0, l2_bids=l2_bids, min_wall_usd=50000.0)
    assert res["passed"] is False
    assert "INSUFFICIENT" in res["reason"]
    assert res["l2_volume_usd"] == 9900.0


def test_confirm_l2_structure_short_pass():
    """Returns pass when an ask wall >= $50k USD exists within 2% of entry price."""
    # Entry at 50,000. Ask wall at 50,500 (1% above) with 2 BTC volume ($101,000 USD)
    l2_asks = [
        [50500.0, 2.0],
        [51000.0, 1.0],
    ]
    res = confirm_l2_structure("BTC-USD", "SHORT", 50000.0, l2_asks=l2_asks, min_wall_usd=50000.0)
    assert res["passed"] is True
    assert res["wall_price"] == 50500.0
    assert res["l2_volume_usd"] == 101000.0


def test_confirm_l2_structure_short_fail_thin_depth():
    """REJECTS setup when orderbook ask wall volume is thin (< $50k USD threshold)."""
    # Entry at 50,000. Ask wall at 50,500 has only 0.2 BTC ($10,100 USD)
    l2_asks = [
        [50500.0, 0.2],
        [51000.0, 0.1],
    ]
    res = confirm_l2_structure("BTC-USD", "SHORT", 50000.0, l2_asks=l2_asks, min_wall_usd=50000.0)
    assert res["passed"] is False
    assert "INSUFFICIENT" in res["reason"]
    assert res["l2_volume_usd"] == 10100.0


def test_persist_rejected_signals_row():
    """Assert _persist_rejected_signals writes row to signals table with status='L2_REJECTED'."""
    import asyncio
    import sqlite3
    from tpt.config.settings import settings
    from tpt.scanner.runner import _persist_rejected_signals

    db_path = settings.sqlite_path
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS signals (
                id TEXT PRIMARY KEY,
                scan_run_id TEXT,
                symbol TEXT,
                timestamp TEXT,
                score REAL,
                score_breakdown TEXT,
                label TEXT,
                trade_direction TEXT,
                entry_price REAL,
                tp_price REAL,
                tp2_price REAL,
                sl_price REAL,
                status TEXT,
                pipeline_version TEXT
            )"""
        )
        conn.execute("DELETE FROM signals WHERE status = 'L2_REJECTED'")
        conn.commit()

    rejected_row = (
        "scan_test_123", "SOL-USD", 72.5,
        '{"l2_gate_result": {"passed": false, "reason": "NO_L2_BID_DATA"}}',
        "ENTRY_ZONE", "LONG", 150.0, 160.0, 165.0, 145.0, "v2.0"
    )
    asyncio.run(_persist_rejected_signals([rejected_row]))

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT symbol, status, score_breakdown FROM signals WHERE status = 'L2_REJECTED'")
        rows = cursor.fetchall()
        assert len(rows) >= 1
        assert rows[0][0] == "SOL-USD"
        assert rows[0][1] == "L2_REJECTED"
        assert "NO_L2_BID_DATA" in rows[0][2]
