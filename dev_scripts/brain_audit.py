"""Audit the decision pipeline ('the brain') from the live database.

Emits JSON so the numbers can be embedded directly into a visualisation.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, "backend")
from tpt.config.settings import settings  # noqa: E402

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "temp_brain_audit.json")

conn = sqlite3.connect(settings.sqlite_path)
conn.row_factory = sqlite3.Row


def one(sql, params=()):
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def rows(sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


result: dict = {"db": settings.sqlite_path}

# ── Latest scan run with data ────────────────────────────────────────────────
latest = one("""
    SELECT id FROM scan_runs
    WHERE status != 'RUNNING'
      AND (SELECT COUNT(*) FROM scores s WHERE s.scan_run_id = scan_runs.id) > 0
    ORDER BY started_at DESC LIMIT 1
""")
result["latest_scan"] = latest
result["scan_run_totals"] = one("SELECT COUNT(*) FROM scan_runs")
result["scan_done"] = one("SELECT COUNT(*) FROM scan_runs WHERE status='DONE'")
result["scan_failed"] = one("SELECT COUNT(*) FROM scan_runs WHERE status='FAILED'")

# ── Ingestion funnel for the latest scan ────────────────────────────────────
if latest:
    result["funnel"] = {
        "products_fetched": one("SELECT symbols_fetched FROM scan_runs WHERE id=?", (latest,)),
        "snapshots": one("SELECT COUNT(*) FROM snapshots WHERE scan_run_id=?", (latest,)),
        "snapshots_with_candles": one(
            "SELECT COUNT(*) FROM snapshots WHERE scan_run_id=? AND raw_candles_1h IS NOT NULL", (latest,)
        ),
        "features": one("SELECT COUNT(*) FROM features WHERE scan_run_id=?", (latest,)),
        "features_with_rsi": one("SELECT COUNT(*) FROM features WHERE scan_run_id=? AND rsi_1h IS NOT NULL", (latest,)),
        "scores": one("SELECT COUNT(*) FROM scores WHERE scan_run_id=?", (latest,)),
        "ladders": one("SELECT COUNT(*) FROM ladders WHERE scan_run_id=?", (latest,)),
    }
    result["labels"] = rows(
        "SELECT label, COUNT(*) AS n FROM scores WHERE scan_run_id=? GROUP BY label ORDER BY n DESC", (latest,)
    )
    result["directions"] = rows(
        "SELECT trade_direction, COUNT(*) AS n FROM scores WHERE scan_run_id=? GROUP BY trade_direction", (latest,)
    )
    result["score_distribution"] = one("""
        SELECT json_object(
            'min', MIN(composite_score), 'p25', 0, 'median', 0, 'p75', 0, 'max', MAX(composite_score),
            'avg', AVG(composite_score)
        ) FROM scores WHERE scan_run_id=?
    """, (latest,))
    # score histogram (10-point buckets)
    result["score_histogram"] = rows("""
        SELECT CAST(composite_score / 10 AS INT) * 10 AS bucket, COUNT(*) AS n
        FROM scores WHERE scan_run_id=? GROUP BY bucket ORDER BY bucket
    """, (latest,))
    # label x direction
    result["label_direction"] = rows("""
        SELECT label, trade_direction, COUNT(*) AS n
        FROM scores WHERE scan_run_id=? GROUP BY label, trade_direction ORDER BY n DESC
    """, (latest,))
    # which components appear in breakdowns (drives the score)
    result["component_usage"] = rows("""
        SELECT COUNT(*) AS n FROM scores WHERE scan_run_id=? AND score_breakdown LIKE '%xgboost_probability%'
    """, (latest,))
    result["ladder_stats"] = rows("""
        SELECT trade_direction,
               COUNT(*) AS n,
               ROUND(AVG(tranche_a_price), 6) AS avg_entry,
               ROUND(AVG(stop_price), 6) AS avg_stop,
               ROUND(AVG(target_1_price), 6) AS avg_t1
        FROM ladders WHERE scan_run_id=? GROUP BY trade_direction
    """, (latest,))
    result["label_ladder_coverage"] = rows("""
        SELECT s.label,
               COUNT(*) AS scored,
               SUM(CASE WHEN l.id IS NOT NULL THEN 1 ELSE 0 END) AS with_ladder
        FROM scores s
        LEFT JOIN ladders l ON l.product_id = s.product_id AND l.scan_run_id = s.scan_run_id
        WHERE s.scan_run_id = ?
        GROUP BY s.label ORDER BY scored DESC
    """, (latest,))

# ── Outcome ledger (the feedback signal) ────────────────────────────────────
result["signals_total"] = one("SELECT COUNT(*) FROM signals")
result["signals_by_status"] = rows("SELECT status, COUNT(*) AS n FROM signals GROUP BY status ORDER BY n DESC")
result["signals_by_label"] = rows("""
    SELECT label, trade_direction,
           COUNT(*) AS n,
           SUM(CASE WHEN status='WIN' THEN 1 ELSE 0 END) AS wins,
           SUM(CASE WHEN status='LOSS' THEN 1 ELSE 0 END) AS losses,
           SUM(CASE WHEN status='PENDING' THEN 1 ELSE 0 END) AS pending,
           ROUND(AVG(score), 1) AS avg_score
    FROM signals GROUP BY label, trade_direction ORDER BY n DESC
""")
result["signals_by_score_band"] = rows("""
    SELECT CAST(score / 10 AS INT) * 10 AS bucket,
           COUNT(*) AS n,
           SUM(CASE WHEN status='WIN' THEN 1 ELSE 0 END) AS wins,
           SUM(CASE WHEN status='LOSS' THEN 1 ELSE 0 END) AS losses,
           SUM(CASE WHEN status='PENDING' THEN 1 ELSE 0 END) AS pending,
           ROUND(AVG(mfe), 3) AS avg_mfe,
           ROUND(AVG(mae), 3) AS avg_mae
    FROM signals GROUP BY bucket ORDER BY bucket
""")
result["signals_rr"] = rows("""
    SELECT symbol, label, trade_direction, score, status,
           entry_price, tp_price, sl_price, mfe, mae, filled_at, closed_at,
           ROUND(ABS(tp_price - entry_price) / NULLIF(ABS(entry_price - sl_price), 0), 2) AS rr
    FROM signals ORDER BY id DESC LIMIT 60
""")
result["signals_filled"] = one("SELECT COUNT(*) FROM signals WHERE filled_at IS NOT NULL")
result["signals_closed"] = one("SELECT COUNT(*) FROM signals WHERE closed_at IS NOT NULL")
result["signals_wins"] = one("SELECT COUNT(*) FROM signals WHERE status='WIN'")
result["component_feedback_rows"] = one("SELECT COUNT(*) FROM component_feedback")

# ── Are the WS/L2 + futures + options inputs actually reaching the brain? ───
result["features_l2_coverage"] = None
if latest:
    result["features_note"] = (
        "features table stores only price/volume/fib/swing columns; "
        "L2, funding and options inputs are transient and NOT persisted."
    )

conn.close()
OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
print(f"wrote {OUT}")
print(json.dumps({k: v for k, v in result.items() if k in (
    "scan_done", "scan_failed", "scan_run_totals", "signals_total", "signals_by_status",
    "signals_filled", "signals_closed", "signals_wins", "component_feedback_rows",
    "labels", "directions", "funnel",
)}, indent=2, default=str))
