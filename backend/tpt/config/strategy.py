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


class ComponentWeights(BaseModel):
    LONG: dict[str, float] = Field(default_factory=dict)
    SHORT: dict[str, float] = Field(default_factory=dict)


class ScoringConfig(BaseModel):
    baseline: int = 50
    component_weights: ComponentWeights = Field(default_factory=ComponentWeights)
    interaction_bonuses: InteractionBonuses = Field(default_factory=InteractionBonuses)
    counter_trend_penalty: float = 15.0


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
    entry_zone_score_min: float = 60


class LadderConfig(BaseModel):
    tranche_a_size_pct: float = 60
    tranche_b_size_pct: float = 40
    stop_pct: float = 3
    fib_a_low: float = 0.50
    fib_a_high: float = 0.618
    fib_b_level: float = 0.786
    target2_extension_pct: float = 5


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
