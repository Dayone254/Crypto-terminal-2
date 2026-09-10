"""Backtest ledger routes — read-only views over the raw `signals` table."""
from __future__ import annotations

import logging
import traceback
from typing import Any

from fastapi import APIRouter, Query

from tpt.data.database import get_connection

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/stats")
async def backtest_stats():
    """Retrieve statistical edge performance."""
    try:
        async with get_connection() as conn:
            async with conn.execute("SELECT status, COUNT(*) as cnt FROM signals GROUP BY status") as cursor:
                rows = await cursor.fetchall()

            counts = {"PENDING": 0, "WIN": 0, "LOSS": 0, "BREAK_EVEN": 0, "ACTIVE_T2": 0, "PARTIAL_WIN": 0}
            for r in rows:
                counts[r["status"]] = r["cnt"]

            total_closed = counts["WIN"] + counts["LOSS"] + counts["BREAK_EVEN"] + counts["PARTIAL_WIN"]
            directional_outcomes = counts["WIN"] + counts["LOSS"]
            # Win rate counts profitable WIN vs LOSS. BREAK_EVEN and PARTIAL_WIN are excluded from directional edge.
            win_rate = (counts["WIN"] / directional_outcomes * 100) if directional_outcomes > 0 else 0.0

            async with conn.execute("SELECT * FROM signals WHERE status IN ('WIN', 'LOSS', 'BREAK_EVEN', 'PARTIAL_WIN') ORDER BY id DESC LIMIT 50") as cursor:
                recent_trades = [dict(r) for r in await cursor.fetchall()]

            async with conn.execute("SELECT * FROM signals WHERE status IN ('PENDING', 'ACTIVE_T2') ORDER BY id DESC") as cursor:
                pending_trades = [dict(r) for r in await cursor.fetchall()]

            return {
                "win_rate": round(win_rate, 2),
                "total_closed": total_closed,
                "wins": counts["WIN"],
                "losses": counts["LOSS"],
                "break_even": counts["BREAK_EVEN"],
                "partial_wins": counts["PARTIAL_WIN"],
                "pending_count": counts["PENDING"] + counts["ACTIVE_T2"],
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
