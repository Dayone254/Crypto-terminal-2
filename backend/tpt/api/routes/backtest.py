"""Backtest ledger routes — read-only views over the raw `signals` table."""
from __future__ import annotations

import logging
import traceback
from typing import Any

from fastapi import APIRouter, Query

from tpt.data.database import get_connection
from tpt.engine.exits import calibrate_targets, excursion_from_signal

router = APIRouter()
logger = logging.getLogger(__name__)

_CLOSED = "('WIN', 'LOSS', 'BREAK_EVEN', 'PARTIAL_WIN')"


def _median(xs: list[float]) -> float | None:
    if not xs:
        return None
    mid = len(xs) // 2
    return xs[mid] if len(xs) % 2 else (xs[mid - 1] + xs[mid]) / 2.0


def _excursion_summary(closed_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """How far trades actually ran, in R — and how many reached their own target.

    A bare win rate cannot distinguish "the entries are wrong" from "the target is
    unreachable". These numbers can. When the win rate sat at 0%, this is the
    evidence that showed the target demanded 2.0R while nothing had ever exceeded
    0.72R — a fact about the target, not about the market.
    """
    excursions = [e for e in (excursion_from_signal(r) for r in closed_rows) if e is not None]
    if not excursions:
        return {
            "n": 0,
            "avg_mfe_r": None,
            "median_mfe_r": None,
            "best_mfe_r": None,
            "avg_mae_r": None,
            "avg_target_r": None,
            "tp1_hits": 0,
            "tp1_hit_rate": 0.0,
        }

    mfe_rs = sorted(e.mfe_r for e in excursions)

    # Did the trade ever reach the target that was published for it? Note this is
    # the target the trade *carried*, which may differ from the one the estimator
    # now proposes — conflating the two produced a sentence claiming 0.72R fell
    # short of 0.25R.
    hits = 0
    target_rs: list[float] = []
    for row in closed_rows:
        exc = excursion_from_signal(row)
        if exc is None:
            continue
        try:
            entry = float(row.get("entry_price"))
            stop = float(row.get("sl_price"))
            target = float(row.get("tp_price"))
        except (TypeError, ValueError):
            continue
        risk = abs(entry - stop)
        if risk <= 0:
            continue
        required_r = abs(target - entry) / risk
        target_rs.append(required_r)
        if exc.mfe_r >= required_r:
            hits += 1

    return {
        "n": len(excursions),
        "avg_mfe_r": round(sum(mfe_rs) / len(mfe_rs), 2),
        "median_mfe_r": round(_median(mfe_rs) or 0.0, 2),
        "best_mfe_r": round(max(mfe_rs), 2),
        "avg_mae_r": round(sum(e.mae_r for e in excursions) / len(excursions), 2),
        # The distance those trades' own targets demanded, so the UI can compare
        # like with like.
        "avg_target_r": round(sum(target_rs) / len(target_rs), 2) if target_rs else None,
        "tp1_hits": hits,
        "tp1_hit_rate": round(hits / len(excursions) * 100.0, 1),
    }


@router.get("/stats")
async def backtest_stats():
    """Retrieve statistical edge performance."""
    try:
        async with get_connection() as conn:
            async with conn.execute("SELECT status, COUNT(*) as cnt FROM signals GROUP BY status") as cursor:
                rows = await cursor.fetchall()

            counts = {"PENDING": 0, "WIN": 0, "LOSS": 0, "BREAK_EVEN": 0, "ACTIVE_T2": 0, "PARTIAL_WIN": 0, "EXPIRED": 0}
            for r in rows:
                counts[r["status"]] = r["cnt"]

            total_closed = counts["WIN"] + counts["LOSS"] + counts["BREAK_EVEN"] + counts["PARTIAL_WIN"]
            directional_outcomes = counts["WIN"] + counts["LOSS"]
            # Win rate counts profitable WIN vs LOSS. BREAK_EVEN and PARTIAL_WIN are excluded from directional edge.
            win_rate = (counts["WIN"] / directional_outcomes * 100) if directional_outcomes > 0 else 0.0

            async with conn.execute(f"SELECT * FROM signals WHERE status IN {_CLOSED} ORDER BY id DESC LIMIT 50") as cursor:
                recent_trades = [dict(r) for r in await cursor.fetchall()]

            async with conn.execute("SELECT * FROM signals WHERE status IN ('PENDING', 'ACTIVE_T2') ORDER BY id DESC") as cursor:
                pending_trades = [dict(r) for r in await cursor.fetchall()]

            # All closed rows (not just the recent 50) feed the excursion summary
            # and the target estimate: the calibration is a property of the whole
            # ledger, and truncating it would bias the estimator.
            async with conn.execute(f"SELECT * FROM signals WHERE status IN {_CLOSED}") as cursor:
                closed_rows = [dict(r) for r in await cursor.fetchall()]

            return {
                "win_rate": round(win_rate, 2),
                "total_closed": total_closed,
                "wins": counts["WIN"],
                "losses": counts["LOSS"],
                "break_even": counts["BREAK_EVEN"],
                "partial_wins": counts["PARTIAL_WIN"],
                "pending_count": counts["PENDING"] + counts["ACTIVE_T2"],
                "expired_count": counts.get("EXPIRED", 0),
                "excursion": _excursion_summary(closed_rows),
                "target_estimate": calibrate_targets(closed_rows).as_dict(),
                "recent": recent_trades,
                "active": pending_trades,
            }
    except Exception:
        logger.error("backtest_stats failed:\n%s", traceback.format_exc())
        return {"error": "Failed to compute backtest stats."}


@router.get("/trades")
async def list_trades(
    status: str = Query(None, description="Filter: PENDING | WIN | LOSS"),
    symbol: str = Query(None, description="Filter by symbol"),
    limit: int = Query(200, le=500),
):
    """Return full trade ledger with optional filters."""
    try:
        async with get_connection() as conn:
            clauses = []
            params: list[Any] = []
            if status:
                clauses.append("status = ?")
                params.append(status.upper())
            if symbol:
                clauses.append("symbol = ?")
                params.append(symbol.upper())
            where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
            params.append(limit)
            async with conn.execute(
                f"SELECT * FROM signals {where} ORDER BY id DESC LIMIT ?",
                params,
            ) as cursor:
                trades = [dict(r) for r in await cursor.fetchall()]
            return {"trades": trades, "count": len(trades)}
    except Exception:
        logger.error("list_trades failed:\n%s", traceback.format_exc())
        return {"trades": [], "count": 0, "error": "Failed to load trades."}


@router.get("/symbols")
async def symbol_breakdown():
    """Return per-symbol win/loss/pending breakdown for the edge leaderboard."""
    try:
        async with get_connection() as conn:
            async with conn.execute(
                """
                SELECT
                    symbol,
                    SUM(CASE WHEN status = 'WIN'         THEN 1 ELSE 0 END) AS wins,
                    SUM(CASE WHEN status = 'LOSS'        THEN 1 ELSE 0 END) AS losses,
                    SUM(CASE WHEN status = 'PARTIAL_WIN' THEN 1 ELSE 0 END) AS partial_wins,
                    SUM(CASE WHEN status IN ('PENDING', 'ACTIVE_T2') THEN 1 ELSE 0 END) AS pending,
                    COUNT(*) AS total,
                    AVG(CASE WHEN status NOT IN ('PENDING', 'ACTIVE_T2') THEN score END) AS avg_score,
                    AVG(mfe) AS avg_mfe,
                    AVG(mae) AS avg_mae
                FROM signals
                GROUP BY symbol
                ORDER BY wins DESC, total DESC
                LIMIT 50
                """
            ) as cursor:
                rows = await cursor.fetchall()

            symbols = []
            for r in rows:
                d = dict(r)
                total_closed = (d["wins"] or 0) + (d["losses"] or 0) + (d["partial_wins"] or 0)
                d["win_rate"] = round(d["wins"] / total_closed * 100, 1) if total_closed > 0 else None
                symbols.append(d)

            return {"symbols": symbols}
    except Exception:
        logger.error("symbol_breakdown failed:\n%s", traceback.format_exc())
        return {"symbols": [], "error": "Failed to load symbol breakdown."}
