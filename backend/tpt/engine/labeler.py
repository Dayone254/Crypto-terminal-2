"""Labeling engine — pure function. No I/O.

Determines exact single primary label using ordered priority tree (SKIP → CHASE → ENTRY_ZONE → COILED → EARLY → WATCH)
and secondary tags dict.
"""
from __future__ import annotations

from typing import Literal

from tpt.config.strategy import LabelingConfig
from tpt.engine.features import FeatureDict

Label = Literal["SKIP", "CHASE", "ENTRY_ZONE", "COILED", "EARLY", "WATCH"]


def compute_tags(
    features: FeatureDict,
    pinned: bool = False,
) -> list[str]:
    """Compute secondary non-exclusive tags for a symbol."""
    tags: list[str] = []

    last_price = float(features.get("last_price") or 0.0)
    vwap = float(features.get("vwap_24h") or 0.0)
    fib_500 = float(features.get("fib_500") or 0.0)
    fib_618 = float(features.get("fib_618") or 0.0)
    swing_shelf = features.get("swing_shelf_7d")
    rsi_1h = features.get("rsi_1h")

    # VWAP Confluence
    if vwap > 0 and abs(last_price - vwap) / vwap <= 0.005:
        tags.append("VWAP_CONFLUENCE")

    # Fib 50% Touch
    if fib_500 > 0 and abs(last_price - fib_500) / fib_500 <= 0.003:
        tags.append("FIB50_TOUCH")

    # Fib 61.8% Touch
    if fib_618 > 0 and abs(last_price - fib_618) / fib_618 <= 0.003:
        tags.append("FIB62_TOUCH")

    # Swing Shelf Near
    if swing_shelf is not None and float(swing_shelf) > 0:
        s_shelf = float(swing_shelf)
        if abs(last_price - s_shelf) / s_shelf <= 0.01:
            tags.append("SWING_SHELF_NEAR")

    # Overbought 1H
    if rsi_1h is not None and float(rsi_1h) > 65.0:
        tags.append("OVERBOUGHT_1H")

    # Pinned
    if pinned:
        tags.append("PINNED")

    # L2 Support / Resistance
    l2_buy_vol = features.get("l2_buy_vol_2pct")
    l2_sell_vol = features.get("l2_sell_vol_2pct")
    if l2_buy_vol is not None and float(l2_buy_vol) >= 100_000.0:
        tags.append("L2_BUY_WALL_SUPPORT")
    if l2_sell_vol is not None and float(l2_sell_vol) >= 100_000.0:
        tags.append("L2_SELL_WALL_REJECTION")

    return tags


def label(
    features: FeatureDict,
    composite_score: float,
    config: LabelingConfig | None = None,
    trade_direction: str = "LONG",
    regime: str = "TRENDING_UP",
    btc_beta_state: str = "RANGING",
) -> Label:
    quote_vol = float(features.get("quote_vol_24h") or 0.0)
    day_change = float(features.get("day_change_pct") or 0.0)
    pos_in_range = float(features.get("pos_in_range") or 0.5)
    last_price = float(features.get("last_price") or 0.0)
    vwap = float(features.get("vwap_24h") or 0.0)

    min_quote_vol = config.min_quote_volume if config else 1_000_000.0
    chase_change = config.chase_change_pct if config else 15.0
    chase_pos = config.chase_pos_threshold if config else 0.80
    coiled_change_low = config.coiled_change_low if config else -3.0
    coiled_change_high = config.coiled_change_high if config else 5.0
    coiled_pos_low = config.coiled_pos_low if config else 0.30
    coiled_pos_high = config.coiled_pos_high if config else 0.65
    early_change_min = config.early_change_min if config else 2.0
    early_pos_max = config.early_pos_max if config else 0.75
    
    # Dynamic entry score based on regime
    entry_score_min = config.entry_zone_score_min if config else 60.0
    if regime == "VOLATILE":
        entry_score_min += 10.0  # Require higher score (70.0) in volatile regimes
    elif regime == "TRENDING_UP" and trade_direction == "LONG":
        entry_score_min -= 5.0   # Relax slightly if trend aligned
    elif regime == "TRENDING_DOWN" and trade_direction == "SHORT":
        entry_score_min -= 5.0

    # Macro Beta Protection Logic (Avoid longing dumps, shorting pumps)
    if trade_direction == "LONG" and btc_beta_state == "DUMPING":
        return "SKIP"
    if trade_direction == "SHORT" and btc_beta_state == "PUMPING":
        return "SKIP"

    # 1. SKIP
    if quote_vol < min_quote_vol:
        return "SKIP"

    if trade_direction == "SHORT":
        # 2. CHASE (Shorting a dump)
        if day_change < -chase_change and pos_in_range < (1.0 - chase_pos):
            return "CHASE"
            
        # 3. ENTRY_ZONE
        in_vwap_pocket = (vwap > 0 and abs(last_price - vwap) / vwap <= 0.005)
        fib_236 = float(features.get("fib_236") or 0.0)
        fib_382 = float(features.get("fib_382") or 0.0)
        lower_fib = min(fib_236, fib_382)
        upper_fib = max(fib_236, fib_382)
        in_fib_zone = (lower_fib > 0 and lower_fib <= last_price <= upper_fib)
        
        if (in_vwap_pocket or in_fib_zone) and composite_score >= entry_score_min:
            return "ENTRY_ZONE"
            
        # 4. COILED (Short Rally)
        if -coiled_change_high <= day_change <= -coiled_change_low and (1.0 - coiled_pos_high) <= pos_in_range <= (1.0 - coiled_pos_low):
            return "COILED"
            
        # 5. EARLY (Short Rejection)
        if day_change < -early_change_min and pos_in_range > (1.0 - early_pos_max):
            return "EARLY"

    else:
        # LONG LOGIC
        # 2. CHASE
        if day_change > chase_change and pos_in_range > chase_pos:
            return "CHASE"

        # 3. ENTRY_ZONE
        in_vwap_pocket = (vwap > 0 and abs(last_price - vwap) / vwap <= 0.005)
        fib_500 = float(features.get("fib_500") or 0.0)
        fib_618 = float(features.get("fib_618") or 0.0)
        lower_fib = min(fib_500, fib_618)
        upper_fib = max(fib_500, fib_618)
        in_fib_zone = (lower_fib > 0 and lower_fib <= last_price <= upper_fib)

        if (in_vwap_pocket or in_fib_zone) and composite_score >= entry_score_min:
            return "ENTRY_ZONE"

        # 4. COILED
        if coiled_change_low <= day_change <= coiled_change_high and coiled_pos_low <= pos_in_range <= coiled_pos_high:
            return "COILED"

        # 5. EARLY
        if day_change > early_change_min and pos_in_range < early_pos_max:
            return "EARLY"

    # 6. WATCH
    return "WATCH"
