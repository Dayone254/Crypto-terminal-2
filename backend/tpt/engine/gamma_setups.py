"""
Gamma Setup Engine
==================
Turns the Gamma Engine's analytics (walls, gamma flip, max pain, pin map,
regime) into actionable setups for the four underlyings with real options
boards: BTC, ETH, SOL, AVAX.

Two consumers:

1. ``build_gamma_enrichment`` — the scanner runner attaches these tags to
   candidate payloads (``score_breakdown`` and candidate dict) so the UI and
   later weighting passes can see the dealer-positioning context. Tags do NOT
   feed the scorer yet: the fixed ``SCORER_INPUTS`` contract keeps scores
   deterministic until the ledger proves which gamma components carry edge.

2. ``run_gamma_shadow_pass`` — a 60s loop that evaluates the three setup
   families and persists candidates as signal rows under the
   ``v3.1-gamma-*`` shadow pipelines. Shadow rows resolve through the normal
   forward evaluator (PENDING -> filled -> TP/SL/BE/EXPIRED), so each family
   accrues an honest track record in the edge ledger before anyone touches
   the live ladder or the scorer.

Honesty rules:
- A family fires only when its evidence exists (no guessed levels).
- Empty or synthetic boards produce nothing.
- Price levels are sanity-checked against live spot before a row is written.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from tpt.config.settings import settings
from tpt.engine.ws_memory import ws_memory

logger = logging.getLogger(__name__)

# Underlyings with real listed options boards on the venues we aggregate.
GAMMA_UNIVERSE = ("BTC", "ETH", "SOL", "AVAX")

# Minimum data-quality gate. Below this the board is too thin (or too stale)
# for levels to mean anything.
MIN_CONFIDENCE_SCORE = 50

_PIN_REVERSION = "v3.1-gamma-pin-reversion"
_WALL_REJECTION = "v3.1-gamma-wall-rejection"
_FLIP_BREAKOUT = "v3.1-gamma-flip-breakout"
GAMMA_PIPELINE_VERSIONS = (_PIN_REVERSION, _WALL_REJECTION, _FLIP_BREAKOUT)

FAMILY_LABELS = {
    _PIN_REVERSION: "GAMMA_PIN_REVERSION",
    _WALL_REJECTION: "GAMMA_WALL_REJECTION",
    _FLIP_BREAKOUT: "GAMMA_FLIP_BREAKOUT",
}

# How long a shadow signal stays PENDING before the evaluator's order-expiry
# reaper expires it. Gamma setups are tactical: if the move hasn't started
# within a few hours the level has drifted.
SETUP_ORDER_EXPIRY_HOURS = 6

# Cooldown per (family, underlying) so one pinned tape doesn't stack rows.
_COOLDOWN_SECONDS = 90.0
_last_fire: dict[str, float] = {}


def _cooldown_ok(key: str) -> bool:
    now = time.monotonic()
    if now - _last_fire.get(key, 0.0) < _COOLDOWN_SECONDS:
        return False
    _last_fire[key] = now
    return True


# ---------------------------------------------------------------------------
# Evidence reader
# ---------------------------------------------------------------------------

def read_gamma_context(underlying: str) -> dict[str, Any] | None:
    """The engine's cached analytics for one underlying, or None when the
    board is missing, synthetic-only, stale, or below the confidence gate."""
    flow = ws_memory.get_macro_options(underlying.upper())
    if not isinstance(flow, dict):
        return None
    if not flow.get("options_available"):
        return None

    venues = ((flow.get("venue_metrics") or {}).get("active_venues")) or []
    if not venues or all("Synthetic" in v for v in venues):
        return None

    spot = float(flow.get("spot_price") or 0.0)
    if spot <= 0:
        return None

    conf = flow.get("confidence") or {}
    if float(conf.get("score") or 0) < MIN_CONFIDENCE_SCORE:
        return None

    return {
        "spot": spot,
        "regime": flow.get("regime"),
        "call_wall": flow.get("call_wall"),
        "put_wall": flow.get("put_wall"),
        "gamma_flip": flow.get("gamma_flip"),
        "max_pain": flow.get("max_pain"),
        "pin_map": flow.get("pin_map") or [],
        "confidence": conf,
        "computed_at": flow.get("computed_at"),
    }


def build_gamma_enrichment(underlying: str) -> dict[str, Any] | None:
    """Compact dealer-positioning context for the scanner runner.

    Cheap by design: reads the ws_memory cache (the 20s sync loop paid for the
    board already), never triggers venue fetches. Returns None silently when
    there is nothing real to say.
    """
    ctx = read_gamma_context(underlying)
    if ctx is None:
        return None
    is_long_gamma = ctx["regime"] == "LONG_GAMMA_STABLE"
    spot = ctx["spot"]
    pin = ctx["pin_map"][0] if ctx["pin_map"] else None

    return {
        "gamma_regime": ctx["regime"],
        "call_wall": ctx["call_wall"],
        "put_wall": ctx["put_wall"],
        "gamma_flip": ctx["gamma_flip"],
        "max_pain": ctx["max_pain"],
        "call_wall_dist_pct": round((ctx["call_wall"] - spot) / spot * 100, 2) if ctx["call_wall"] else None,
        "put_wall_dist_pct": round((ctx["put_wall"] - spot) / spot * 100, 2) if ctx["put_wall"] else None,
        "gamma_flip_dist_pct": round((ctx["gamma_flip"] - spot) / spot * 100, 2) if ctx["gamma_flip"] else None,
        "top_pin_strike": pin.get("strike") if pin else None,
        "top_pin_dist_pct": pin.get("dist_pct") if pin else None,
        "top_pin_strength": pin.get("strength") if pin else None,
        "long_gamma": is_long_gamma,
        "confidence_score": ctx["confidence"].get("score"),
        "confidence_grade": ctx["confidence"].get("grade"),
    }


# ---------------------------------------------------------------------------
# Setup families
# ---------------------------------------------------------------------------

def _near(a: float, b: float, tol_pct: float) -> bool:
    if a <= 0 or b <= 0:
        return False
    return abs(a - b) / b <= tol_pct / 100.0


def _make_row(
    *, pipeline_version: str, symbol: str, direction: str, spot: float,
    stop: float, target: float, secondary: float | None, confidence: dict,
    regime: str, setup_note: str,
) -> dict[str, Any] | None:
    """One shadow signal row with levels sanity-checked against live spot."""
    if spot <= 0 or stop <= 0 or target <= 0:
        return None
    risk = abs(spot - stop)
    reward = abs(target - spot)
    if risk <= 0 or reward <= 0:
        return None
    rr = reward / risk
    if rr < 0.8:  # refuse incoherent geometry; don't manufacture a bad trade
        return None

    entry = round(spot, 8)
    return {
        "pipeline_version": pipeline_version,
        "symbol": symbol,
        "label": FAMILY_LABELS[pipeline_version],
        "trade_direction": direction,
        "entry_price": entry,
        "tp_price": round(target, 8),
        "tp2_price": round(secondary if secondary else target, 8),
        "sl_price": round(stop, 8),
        "score": 0.0,  # not scorer-ranked; the family IS the signal
        "score_breakdown": json.dumps({
            "setup_family": FAMILY_LABELS[pipeline_version],
            "note": setup_note,
            "gamma_regime": regime,
            "confidence_score": confidence.get("score"),
            "confidence_grade": confidence.get("grade"),
        }),
        "position_size_usd": 100.0,
        "status": "PENDING",
    }


def _setup_pin_reversion(ctx: dict[str, Any], base: str, spot: float) -> dict[str, Any] | None:
    """LONG gamma: price stretched from max pain fades back to the magnet.

    Max pain is the expiry-magnet level; in long gamma dealers defend it by
    buying dips / selling rallies. A >1.2% stretch is enough stretch to fade
    while the pin still dominates the tape.
    """
    mp = ctx.get("max_pain")
    if not mp or ctx.get("regime") != "LONG_GAMMA_STABLE":
        return None
    stretch_pct = (spot - mp) / mp * 100.0
    if abs(stretch_pct) < 1.2:
        return None
    if stretch_pct > 0:
        # Price above the pin: fade back DOWN to it.
        return _make_row(
            pipeline_version=_PIN_REVERSION, symbol=f"{base}-USD", direction="SHORT",
            spot=spot, stop=spot * 1.012, target=mp,
            secondary=mp + (spot - mp) * 0.5, confidence=ctx["confidence"],
            regime=ctx["regime"],
            setup_note=f"long-gamma fade toward max pain {mp:.0f} ({stretch_pct:+.2f}% stretch)",
        )
    return _make_row(
        pipeline_version=_PIN_REVERSION, symbol=f"{base}-USD", direction="LONG",
        spot=spot, stop=spot * 0.988, target=mp,
        secondary=mp + (spot - mp) * 0.5, confidence=ctx["confidence"],
        regime=ctx["regime"],
        setup_note=f"long-gamma fade toward max pain {mp:.0f} ({stretch_pct:+.2f}% stretch)",
    )


def _setup_wall_rejection(ctx: dict[str, Any], base: str, spot: float) -> dict[str, Any] | None:
    """LONG gamma: price pressed into a defended wall fades off it.

    Long gamma means dealers buy dips at the put wall and sell rallies into
    the call wall. Touching a wall inside a 0.35% band with a flip between
    spot and the wall (so the wall is the proximate magnet, not a distant
    level) is the rejection zone.
    """
    if ctx.get("regime") != "LONG_GAMMA_STABLE":
        return None
    flip = ctx.get("gamma_flip") or 0.0

    call_wall = ctx.get("call_wall")
    if call_wall and _near(spot, call_wall, 0.35) and flip < spot < call_wall:
        return _make_row(
            pipeline_version=_WALL_REJECTION, symbol=f"{base}-USD", direction="SHORT",
            spot=spot, stop=call_wall * 1.004, target=flip,
            secondary=(spot + flip) / 2.0, confidence=ctx["confidence"],
            regime=ctx["regime"],
            setup_note=f"call-wall rejection at {call_wall:.0f}, magnet {flip:.0f}",
        )

    put_wall = ctx.get("put_wall")
    if put_wall and _near(spot, put_wall, 0.35) and put_wall < spot < flip:
        return _make_row(
            pipeline_version=_WALL_REJECTION, symbol=f"{base}-USD", direction="LONG",
            spot=spot, stop=put_wall * 0.996, target=flip,
            secondary=(spot + flip) / 2.0, confidence=ctx["confidence"],
            regime=ctx["regime"],
            setup_note=f"put-wall rejection at {put_wall:.0f}, magnet {flip:.0f}",
        )
    return None


def _setup_flip_breakout(ctx: dict[str, Any], base: str, spot: float) -> dict[str, Any] | None:
    """Confirmed regime flip: momentum continuation, wide first target.

    Uses the GammaRegimeTracker's committed transitions (10-minute hold
    filter), so whipsaw near the flip line never fires this. Recent flip
    plus spot beyond the flip level with momentum room to the far wall.
    """
    transitions = []
    try:
        from tpt.engine.gamma_analytics import get_regime_tracker
        transitions = get_regime_tracker().transitions(base.upper()) or []
    except Exception:
        return None
    if not transitions:
        return None
    latest = transitions[-1]
    if time.time() - float(latest.get("ts") or 0) > 90 * 60:
        return None
    to_regime = latest.get("to")
    flip = ctx.get("gamma_flip")
    if not flip or to_regime not in ("LONG_GAMMA_STABLE", "SHORT_GAMMA_VOLATILE"):
        return None

    if to_regime == "LONG_GAMMA_STABLE" and spot > flip:
        target = ctx.get("call_wall") or spot * 1.03
        stop = flip * 0.997
        if target <= spot or stop >= spot:
            return None
        return _make_row(
            pipeline_version=_FLIP_BREAKOUT, symbol=f"{base}-USD", direction="LONG",
            spot=spot, stop=stop, target=target,
            secondary=spot + (target - spot) * 0.5, confidence=ctx["confidence"],
            regime=to_regime,
            setup_note=f"confirmed flip to LONG gamma at {latest.get('spot'):.0f}; momentum to call wall",
        )
    if to_regime == "SHORT_GAMMA_VOLATILE" and spot < flip:
        target = ctx.get("put_wall") or spot * 0.97
        stop = flip * 1.003
        if target >= spot or stop <= spot:
            return None
        return _make_row(
            pipeline_version=_FLIP_BREAKOUT, symbol=f"{base}-USD", direction="SHORT",
            spot=spot, stop=stop, target=target,
            secondary=spot - (spot - target) * 0.5, confidence=ctx["confidence"],
            regime=to_regime,
            setup_note=f"confirmed flip to SHORT gamma at {latest.get('spot'):.0f}; momentum to put wall",
        )
    return None


FAMILIES = (
    (_PIN_REVERSION, _setup_pin_reversion),
    (_WALL_REJECTION, _setup_wall_rejection),
    (_FLIP_BREAKOUT, _setup_flip_breakout),
)


# ---------------------------------------------------------------------------
# Shadow pass
# ---------------------------------------------------------------------------

async def _persist_gamma_signals(rows: list[dict[str, Any]]) -> int:
    """Insert gamma shadow rows. Never duplicates an open row for the same
    (pipeline, symbol); honors the global write lock."""
    if not rows:
        return 0
    from tpt.data.database import get_connection
    from tpt.db.write_lock import db_write_lock

    inserted = 0
    async with db_write_lock:
        async with get_connection() as conn:
            for r in rows:
                pv = r["pipeline_version"]
                sym = r["symbol"]
                async with conn.execute(
                    """SELECT id FROM signals
                       WHERE pipeline_version = ? AND symbol = ?
                         AND status IN ('PENDING', 'IN_TRADE', 'ACTIVE_T2')""",
                    (pv, sym),
                ) as cur:
                    if await cur.fetchone():
                        continue
                await conn.execute(
                    """INSERT INTO signals
                       (symbol, timestamp, score, score_breakdown, label, trade_direction,
                        entry_price, tp_price, tp2_price, sl_price, position_size_usd,
                        status, pipeline_version)
                       VALUES (?, strftime('%s','now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        sym, r["score"], r["score_breakdown"], r["label"],
                        r["trade_direction"], r["entry_price"], r["tp_price"],
                        r["tp2_price"], r["sl_price"], r["position_size_usd"],
                        r["status"], pv,
                    ),
                )
                inserted += 1
            await conn.commit()
    return inserted


async def run_gamma_shadow_pass() -> dict[str, int]:
    """One evaluation pass over the gamma universe. Returns per-family insert
    counts (for logging/tests). All failures are contained; never raises."""
    fired: dict[str, int] = {}
    rows: list[dict[str, Any]] = []
    for base in GAMMA_UNIVERSE:
        ctx = read_gamma_context(base)
        if ctx is None:
            continue
        spot = ctx["spot"]
        for pv, generator in FAMILIES:
            try:
                row = generator(ctx, base, spot)
            except Exception:
                logger.exception("Gamma setup %s failed for %s", pv, base)
                continue
            if row is None:
                continue
            if not _cooldown_ok(f"{pv}:{base}"):
                continue
            rows.append(row)
            fired[pv] = fired.get(pv, 0) + 1
    if rows:
        try:
            await _persist_gamma_signals(rows)
        except Exception:
            logger.exception("Gamma shadow persistence failed")
            return {}
    return fired


async def gamma_shadow_loop() -> None:
    """Background pass every 60s, started from the API lifespan."""
    await asyncio.sleep(120.0)  # let the first options sync populate the cache
    while True:
        try:
            fired = await run_gamma_shadow_pass()
            if fired:
                logger.info("Gamma setup engine fired: %s", fired)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Gamma shadow loop error")
        await asyncio.sleep(60.0)


# ---------------------------------------------------------------------------
# Shadow pipeline registration
# ---------------------------------------------------------------------------

def ensure_gamma_shadow_pipelines() -> None:
    """Register the three gamma families in shadow_pipelines as STAGED.

    Inserted directly (not via stage_candidate_strategy) because that helper
    hardcodes the v3.0- prefix; gamma candidates live in the v3.1- namespace
    so walk-forward candidate versions can never collide with them.
    """
    import sqlite3

    from tpt.config.settings import settings as _settings

    target_n = _settings.min_shadow_sample_size
    conn = sqlite3.connect(_settings.sqlite_path, timeout=10.0)
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS shadow_pipelines (
                   pipeline_version TEXT PRIMARY KEY,
                   candidate_name TEXT,
                   staged_at TEXT,
                   sample_count INTEGER DEFAULT 0,
                   target_sample_size INTEGER,
                   status TEXT DEFAULT 'STAGED',
                   config_json TEXT,
                   promoted_at TEXT
               )"""
        )
        for pv in GAMMA_PIPELINE_VERSIONS:
            conn.execute(
                """INSERT OR IGNORE INTO shadow_pipelines
                   (pipeline_version, candidate_name, staged_at, sample_count,
                    target_sample_size, status, config_json)
                   VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'), 0, ?, 'STAGED', ?)""",
                (
                    pv,
                    FAMILY_LABELS[pv],
                    target_n,
                    json.dumps({
                        "engine": "gamma_setups",
                        "universe": list(GAMMA_UNIVERSE),
                        "min_confidence_score": MIN_CONFIDENCE_SCORE,
                        "order_expiry_hours": SETUP_ORDER_EXPIRY_HOURS,
                    }),
                ),
            )
        conn.commit()
    finally:
        conn.close()
