"""Strategy config loader — reads and validates config/strategy.yaml.

Runtime weight overrides are persisted by `PATCH /api/v1/config/scoring` into the
`user_settings` table of the **active** database. This module reads them back
from the same file (`settings.sqlite_path`) so the save/reload round-trip holds.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from tpt.config.settings import settings

logger = logging.getLogger(__name__)

STRATEGY_PATH = Path(__file__).parent.parent.parent.parent / "config" / "strategy.yaml"


class InteractionBonuses(BaseModel):
    confluence_bonus: float = 10.0
    breakout_bonus: float = 8.0
    # Awarded when BB squeeze + volume surge + 1h RS or L2 absorption fire together
    # on a coin that has not yet made its 5%+ expansion move. Helps pre-breakout
    # coils clear the entry-score gate so they surface as EARLY setups.
    pre_breakout_coil_bonus: float = 12.0


# Default component weights. These must mirror config/strategy.yaml: a
# `ScoringConfig()` built without the YAML (as the unit tests and any caller that
# omits a config do) previously fell back to an *empty* weight map, which silently
# degraded the scorer to baseline-plus-interactions and reported zero coverage.
_DEFAULT_LONG_WEIGHTS: dict[str, float] = {
    "liquidity": 0.10,
    "trend_strength": 0.25,
    "volatility_compression": 0.10,
    "momentum": 0.25,
    "relative_strength": 0.20,
    "l2_support": 0.10,
}

_DEFAULT_SHORT_WEIGHTS: dict[str, float] = {
    "liquidity": 0.10,
    "trend_weakness": 0.25,
    "volatility_expansion": 0.10,
    "momentum": 0.25,
    "relative_weakness": 0.20,
    "l2_resistance": 0.10,
}


class ComponentWeights(BaseModel):
    LONG: dict[str, float] = Field(default_factory=lambda: dict(_DEFAULT_LONG_WEIGHTS))
    SHORT: dict[str, float] = Field(default_factory=lambda: dict(_DEFAULT_SHORT_WEIGHTS))


class ScoringConfig(BaseModel):
    baseline: int = 50
    component_weights: ComponentWeights = Field(default_factory=ComponentWeights)
    interaction_bonuses: InteractionBonuses = Field(default_factory=InteractionBonuses)
    # Graded replacement for the old hard SKIP on a hostile BTC push. Points
    # removed at full headwind, and the thrust (percent) at which it saturates.
    # A penalty rather than a veto, so an exceptional setup can still qualify:
    # a broad BTC dump is exactly when the strongest relative performers matter.
    macro_beta_penalty: float = 18.0
    macro_beta_full_at_pct: float = 3.0


class LabelingConfig(BaseModel):
    min_quote_volume: float = 1_000_000
    chase_change_pct: float = 15
    chase_pos_threshold: float = 0.80
    coiled_change_low: float = -3
    coiled_change_high: float = 5
    coiled_pos_low: float = 0.30
    coiled_pos_high: float = 0.65
    early_change_min: float = 2
    early_pos_max: float = 0.75
    # Fix 1: Hard gate (based on COILED WR 12.9% / ENTRY_ZONE 0%)
    min_composite_score: float = 60


class LadderConfig(BaseModel):
    tranche_a_size_pct: float = 60
    tranche_b_size_pct: float = 40
    stop_pct: float = 3
    fib_a_low: float = 0.50
    fib_a_high: float = 0.618
    fib_b_level: float = 0.786
    target2_extension_pct: float = 5

    # ── Risk sizing ──────────────────────────────────────────────────────────
    # The stop is bounded using the instrument's own 1h ATR, so an R means
    # roughly the same thing across assets of wildly differing volatility. The
    # old logic used a flat 3% stop with a 5% clamp, which on an asset whose
    # whole favourable excursion is 1-3% left R so wide that every R-multiple
    # target was unreachable.
    atr_stop_mult: float = 1.5   # risk = this many 1h ATRs, before bounding
    min_stop_pct: float = 1.0    # percent of entry: never stop inside the noise
    # Fix 3: Loosen the ATR stop clamp based on Avg MAE of -4.39% 
    max_stop_pct: float = 6.0    # percent of entry: never so wide R dwarfs the move
    # Fix 4: Order expiry for stale pending signals
    order_expiry_hours: int = 6


    # ── Exit management ──────────────────────────────────────────────────────
    # Break-even arming, in R: the stop moves to entry once the trade has earned
    # this much of its own risk back. This replaces a flat `mfe >= 2.5` PERCENT,
    # which on a 5% stop armed at 0.5R and converted eight of the first 22 closed
    # trades into break-evens.
    be_arm_r: float = 1.0


class AlertConfig(BaseModel):
    dedupe_hours: int = 6
    quiet_hours_start: str = "00:00"
    quiet_hours_end: str = "07:59"
    timezone: str = "Africa/Nairobi"
    digest_time: str = "08:00"


class StrategyConfig(BaseModel):
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    labeling: LabelingConfig = Field(default_factory=LabelingConfig)
    ladder: LadderConfig = Field(default_factory=LadderConfig)
    alerts: AlertConfig = Field(default_factory=AlertConfig)


_cached_config: StrategyConfig | None = None
_cached_mtime: float = 0.0

# The PATCH route historically wrote `{"components": ...}` while this loader
# expected `{"component_weights": ...}`. Accept both so old saved overrides keep
# working after the fix.
_COMPONENT_ALIASES = ("component_weights", "components")


def _load_db_overrides() -> dict:
    """Synchronously load scoring-weight overrides from the active SQLite DB."""
    db_path = settings.sqlite_path
    if not os.path.exists(db_path):
        return {}
    try:
        conn = sqlite3.connect(db_path, timeout=5.0)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM user_settings WHERE key = 'scoring_weights_override'")
            row = cursor.fetchone()
        finally:
            conn.close()
        if row and row[0]:
            return json.loads(row[0])
    except Exception as exc:
        logger.warning("Could not load scoring overrides from %s: %s", db_path, exc)
    return {}


def _extract_weight_map(overrides: dict) -> dict | None:
    """Pull the per-direction weight map out of either override shape."""
    for key in _COMPONENT_ALIASES:
        candidate = overrides.get(key)
        if isinstance(candidate, dict):
            return candidate
    return None


def load_strategy(force_reload: bool = False) -> StrategyConfig:
    """Load strategy.yaml and apply DB overrides."""
    global _cached_config, _cached_mtime
    path = STRATEGY_PATH

    if path.exists():
        mtime = os.path.getmtime(path)
        if force_reload or _cached_config is None or mtime > _cached_mtime:
            with open(path) as f:
                raw = yaml.safe_load(f) or {}

            weight_map = _extract_weight_map(_load_db_overrides())
            if weight_map and "scoring" in raw:
                raw.setdefault("scoring", {}).setdefault("component_weights", {})
                for direction, weights in weight_map.items():
                    if direction in raw["scoring"]["component_weights"] and isinstance(weights, dict):
                        raw["scoring"]["component_weights"][direction].update(weights)

            _cached_config = StrategyConfig.model_validate(raw)
            _cached_mtime = mtime
    else:
        _cached_config = StrategyConfig()
    return _cached_config


strategy_config = load_strategy()
