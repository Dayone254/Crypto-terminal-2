import json
import logging
from datetime import UTC, datetime

from tpt.data.database import get_connection

logger = logging.getLogger(__name__)

# Only NAMED weighted components may appear in a hit-rate. score_breakdown also
# carries display metadata (coverage, backed, feature_version, funding_rate, ...) —
# counting those as "components" produced hit rates for keys that never scored
# anything. The lists mirror belief.py's _SOURCES maps.
_COMPONENT_KEYS = frozenset({
    "liquidity", "trend_strength", "relative_strength", "volatility_compression",
    "momentum", "l2_support", "trend_weakness", "relative_weakness",
    "volatility_expansion", "l2_resistance",
})


async def get_component_feedback() -> list[dict]:
    """Read the computed component hit rates (previously write-only)."""
    from tpt.data.database import get_connection

    async with get_connection() as conn, conn.execute(
        "SELECT component, hit_rate, total_occurrences, last_computed_at "
        "FROM component_feedback ORDER BY total_occurrences DESC"
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]

async def compute_signal_feedback(min_count: int = 50):
    """
    Analyze closed signals to identify which scoring components correlate with wins.
    Only computes feedback if the number of closed signals exceeds `min_count` to prevent overfitting to small samples.
    """
    async with get_connection() as conn, conn.execute(
        "SELECT * FROM signals WHERE status IN ('WIN', 'LOSS', 'PARTIAL_WIN', 'BREAK_EVEN')"
    ) as cur:
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

        # Only the components that actually carried weight in this trade's
        # score. Display/metadata keys (coverage, backed, feature_version, …)
        # are skipped — iterating the whole breakdown used to compute hit
        # rates for keys that never scored anything.
        for component, val in breakdown.items():
            if component not in _COMPONENT_KEYS or not isinstance(val, (int, float)):
                continue
            if component not in stats:
                stats[component] = {"wins": 0, "total": 0, "active_wins": 0, "active": 0}

            stats[component]["total"] += 1
            if is_win:
                stats[component]["wins"] += 1
            # Conditioning: how often did this component FIRE (|value| > 0.05),
            # and how often did it fire on a winner? A component whose hit rate
            # matches the base rate teaches nothing when it is silent.
            if abs(float(val)) > 0.05:
                stats[component]["active"] += 1
                if is_win:
                    stats[component]["active_wins"] += 1

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

    # The conditioning rate is where the leverage is: a component that fires on
    # winners far above the ledger's base win rate is the one worth up-weighting.
    for component, counts in stats.items():
        if counts.get("active", 0) >= 10:
            logger.info(
                "[feedback] %s: base hit %.1f%% (%d trades), active hit %.1f%% (%d fires)",
                component,
                counts["wins"] / counts["total"] * 100.0,
                counts["total"],
                counts["active_wins"] / counts["active"] * 100.0,
                counts["active"],
            )
    return stats
    
    logger.info(f"Feedback loop computation complete over {len(closed)} closed signals.")
