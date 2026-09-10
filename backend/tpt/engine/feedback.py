import json
import logging
from datetime import UTC, datetime

from tpt.data.database import get_connection

logger = logging.getLogger(__name__)

async def compute_signal_feedback(min_count: int = 50):
    """
    Analyze closed signals to identify which scoring components correlate with wins.
    Only computes feedback if the number of closed signals exceeds `min_count` to prevent overfitting to small samples.
    """
    async with get_connection() as conn:
        async with conn.execute("SELECT * FROM signals WHERE status IN ('WIN', 'LOSS', 'PARTIAL_WIN', 'BREAK_EVEN')") as cur:
            closed = await cur.fetchall()

    if len(closed) < min_count:
        logger.info(f"Not enough closed signals to compute feedback (found {len(closed)}, need {min_count})")
        return

    stats = {}

    for row in closed:
        sig = dict(row)
        score_breakdown_raw = sig.get("score_breakdown")
        if not score_breakdown_raw:
            continue
            
        try:
            breakdown = json.loads(score_breakdown_raw)
        except Exception:
            continue

        status = sig["status"]
        # Consider WIN and PARTIAL_WIN as a successful directional setup
        is_win = status in ("WIN", "PARTIAL_WIN")

        for component, val in breakdown.items():
            if component not in stats:
                stats[component] = {"wins": 0, "total": 0}
            
            stats[component]["total"] += 1
            if is_win:
                stats[component]["wins"] += 1

    async with get_connection() as conn:
        for component, counts in stats.items():
            total = counts["total"]
            # 10 occurrences minimum needed to start recording hit rate internally
            if total >= 10:
                hit_rate = counts["wins"] / total
                now_str = datetime.now(UTC).isoformat()
                await conn.execute(
                    """
                    INSERT INTO component_feedback (component, hit_rate, total_occurrences, last_computed_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(component) DO UPDATE SET 
                        hit_rate = excluded.hit_rate,
                        total_occurrences = excluded.total_occurrences,
                        last_computed_at = excluded.last_computed_at
                    """,
                    (component, hit_rate, total, now_str)
                )
        await conn.commit()
    
    logger.info(f"Feedback loop computation complete over {len(closed)} closed signals.")
