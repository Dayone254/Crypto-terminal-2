"""
Options OI History — 24h flow deltas
====================================
Persists hourly per-strike OI snapshots so the Gamma Engine can show *change*
in positioning (whale trails), not just the standing book. Rows live in the
main SQLite DB next to the signals ledger.

Schema (created lazily):
    options_oi_history(
        id INTEGER PK AUTOINCREMENT,
        underlying TEXT NOT NULL,
        ts INTEGER NOT NULL,           -- unix seconds
        total_oi_usd REAL, call_oi_usd REAL, put_oi_usd REAL,
        strikes_json TEXT              -- {"<strike>": {"C": oi, "P": oi}, ...}
    )
    + index on (underlying, ts)
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from tpt.data.database import get_connection

logger = logging.getLogger(__name__)

_SNAPSHOT_INTERVAL_SECONDS = 3600.0
_BASELINE_WINDOW = (18.0 * 3600.0, 30.0 * 3600.0)  # 24h ± 6h tolerance
_RETENTION_SECONDS = 8 * 86400.0

_LAST_SNAPSHOT_TS: dict[str, float] = {}
_TABLE_READY = False


async def _ensure_table(conn) -> None:
    global _TABLE_READY
    if _TABLE_READY:
        return
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS options_oi_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            underlying TEXT NOT NULL,
            ts INTEGER NOT NULL,
            total_oi_usd REAL NOT NULL DEFAULT 0,
            call_oi_usd REAL NOT NULL DEFAULT 0,
            put_oi_usd REAL NOT NULL DEFAULT 0,
            strikes_json TEXT NOT NULL DEFAULT '{}'
        )
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_oi_hist_sym_ts ON options_oi_history(underlying, ts)"
    )
    await conn.commit()
    _TABLE_READY = True


def _aggregate_board(board: list[dict]) -> tuple[float, float, float, dict[float, dict[str, float]]]:
    total = call = put = 0.0
    strikes: dict[float, dict[str, float]] = {}
    for opt in board:
        try:
            oi = float(opt.get("open_interest", 0) or 0)
            k = float(opt.get("strike", 0) or 0)
            px = float(opt.get("underlying_price", 0) or 0)
        except (TypeError, ValueError):
            continue
        if oi <= 0 or k <= 0:
            continue
        oi_usd = oi * px
        otype = "C" if str(opt.get("type", "")).upper() in ("C", "CALL") else "P"
        total += oi_usd
        if otype == "C":
            call += oi_usd
        else:
            put += oi_usd
        strikes.setdefault(k, {})[otype] = strikes.get(k, {}).get(otype, 0.0) + oi
    return total, call, put, strikes


async def maybe_record_snapshot(underlying: str, board: list[dict]) -> bool:
    """Record an hourly snapshot at most once per interval. Returns True when
    a snapshot was written. Empty boards never overwrite history."""
    if not board:
        return False
    now = time.time()
    last = _LAST_SNAPSHOT_TS.get(underlying, 0.0)
    if now - last < _SNAPSHOT_INTERVAL_SECONDS:
        return False

    total, call, put, strikes = _aggregate_board(board)
    if total <= 0:
        return False

    payload = json.dumps(
        {f"{k:.10g}": v for k, v in strikes.items()},
        separators=(",", ":"),
    )
    try:
        async with get_connection() as conn:
            await _ensure_table(conn)
            await conn.execute(
                """INSERT INTO options_oi_history
                       (underlying, ts, total_oi_usd, call_oi_usd, put_oi_usd, strikes_json)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (underlying, int(now), total, call, put, payload),
            )
            await conn.execute(
                "DELETE FROM options_oi_history WHERE ts < ?",
                (int(now - _RETENTION_SECONDS),),
            )
            await conn.commit()
    except Exception as exc:
        logger.warning("OI snapshot failed for %s: %s", underlying, exc)
        return False

    _LAST_SNAPSHOT_TS[underlying] = now
    return True


async def get_baseline(underlying: str, now: float | None = None) -> dict[str, Any] | None:
    """The newest snapshot inside the ~24h window, or None (no flow baseline)."""
    now = time.time() if now is None else now
    lo, hi = _BASELINE_WINDOW
    try:
        async with get_connection() as conn:
            await _ensure_table(conn)
            async with conn.execute(
                """SELECT ts, total_oi_usd, call_oi_usd, put_oi_usd, strikes_json
                   FROM options_oi_history
                   WHERE underlying = ? AND ts BETWEEN ? AND ?
                   ORDER BY ts DESC LIMIT 1""",
                (underlying, int(now - hi), int(now - lo)),
            ) as cur:
                row = await cur.fetchone()
    except Exception as exc:
        logger.warning("OI baseline lookup failed for %s: %s", underlying, exc)
        return None
    if row is None:
        return None
    return {
        "ts": row[0],
        "total_oi_usd": row[1],
        "call_oi_usd": row[2],
        "put_oi_usd": row[3],
        "strikes": json.loads(row[4]),
    }


async def compute_oi_flow(
    underlying: str, board: list[dict], top_n: int = 3,
    expiry_filter: str | None = None,
) -> dict[str, Any] | None:
    """24h change in positioning: totals + biggest per-strike OI moves.

    Band-filtered boards (0DTE/7D/30D) return None: stored snapshots are
    whole-chain, so band-vs-chain deltas fabricate flows (every 0DTE
    settlement would book as a giant outflow against the ALL baseline)."""
    if expiry_filter and str(expiry_filter).upper() not in ("", "ALL"):
        return None
    baseline = await get_baseline(underlying)
    if baseline is None:
        return None

    total, call, put, strikes = _aggregate_board(board)
    if total <= 0:
        return None

    b_strikes: dict[float, dict[str, float]] = {}
    for k_str, v in baseline.get("strikes", {}).items():
        try:
            b_strikes[float(k_str)] = {t: float(x) for t, x in v.items()}
        except (TypeError, ValueError):
            continue

    deltas: list[dict[str, Any]] = []
    seen = set(strikes) | set(b_strikes)
    for k in seen:
        cur = strikes.get(k, {})
        old = b_strikes.get(k, {})
        d_call = cur.get("C", 0.0) - old.get("C", 0.0)
        d_put = cur.get("P", 0.0) - old.get("P", 0.0)
        d_total = d_call + d_put
        if abs(d_total) < 1e-6:
            continue
        deltas.append({
            "strike": k,
            "delta_oi_usd": d_total,
            "delta_call_usd": d_call,
            "delta_put_usd": d_put,
        })
    deltas.sort(key=lambda d: abs(d["delta_oi_usd"]), reverse=True)

    return {
        "hours": round((time.time() - baseline["ts"]) / 3600.0, 1),
        "delta_total_usd": total - baseline["total_oi_usd"],
        "delta_call_usd": call - baseline["call_oi_usd"],
        "delta_put_usd": put - baseline["put_oi_usd"],
        "top_strikes": [
            {
                "strike": d["strike"],
                "delta_oi_usd": round(d["delta_oi_usd"], 0),
                "side": ("CALLS" if d["delta_call_usd"] >= d["delta_put_usd"] else "PUTS"),
            }
            for d in deltas[:top_n]
        ],
    }
