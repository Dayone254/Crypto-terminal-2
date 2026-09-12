"""Scoring engine — pure function. No I/O.

Computes a composite setup quality score [0, 100] from features using
normalized features and config-driven component weights.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import joblib

from tpt.config.settings import settings
from tpt.config.strategy import ScoringConfig
from tpt.engine.belief import (
    FEATURE_VERSION,
    availability,
    coverage_band,
    edge_and_coverage,
    rank_key,
    shrink_interactions,
)
from tpt.engine.features import FeatureDict

logger = logging.getLogger(__name__)

# Relative strength is measured on the 7-day horizon (see features.py) so that it
# is not an affine copy of the 24h trend component. A 7d outperformance of
# `RS_7D_SCALE` percent is treated as a full-strength signal.
RS_7D_SCALE = 8.0
# Points awarded per percent of 7d outperformance, capped at the historical 15.
RS_7D_BONUS_FACTOR = 1.5

ScoreBreakdown = dict[str, Any]

_xgb_model = None
_xgb_loaded = False

def _get_xgb_model():
    global _xgb_model, _xgb_loaded
    # Opt-in only. The model consumes options-flow features that exist for
    # BTC/ETH alone; for every other coin they are fed as hard-coded 0.0, which
    # the model treats as a real observation and mis-scores. See
    # settings.enable_ml_scoring. The config-driven path below is the default.
    if not settings.enable_ml_scoring:
        return None
    if not _xgb_loaded:
        _xgb_loaded = True
        model_path = os.path.join(os.path.dirname(__file__), 'taperadar_xgboost_v1.joblib')
        if os.path.exists(model_path):
            try:
                _xgb_model = joblib.load(model_path)
                print(">>> [SCORER] Loaded Machine Learning Binary: taperadar_xgboost_v1.joblib")
            except Exception as e:
                print(f"Failed to load XGBoost: {e}")
    return _xgb_model

def normalize_features(features: FeatureDict, direction: str) -> dict[str, float]:
    """Map raw features to [-1.0, 1.0] for weighted dot product.

    Calibration Notes (V3.1):
    - Absent/neutral features must normalize to 0.0, NOT -1.0, to avoid
      phantom penalties that flatten the entire score distribution.
    - Ranges are tuned to crypto-specific distributions:
        * Daily change: ±5% is a strong signal (not ±10%)
        * Liquidity: $1M is the SKIP floor; $5M+ is strong
        * L2 volume: 0 → 0.0 (neutral), $100K+ → positive signal
        * RSI: 30-70 is the operating band; extremes are ±1.0
    """
    norm: dict[str, float] = {}

    quote_vol = float(features.get("quote_vol_24h") or 0.0)
    day_change = float(features.get("day_change_pct") or 0.0)
    pos_in_range = float(features.get("pos_in_range") or 0.5)
    # 7-day relative strength vs BTC. None when daily history is too short — the
    # component is then reported *unavailable* (shrinking coverage) instead of
    # being scored as a neutral zero, which would fake a real observation.
    _rs7 = features.get("rs_vs_btc_7d")
    rs_vs_btc_7d = float(_rs7) if _rs7 is not None else None
    rsi_1h = float(features.get("rsi_1h") or 50.0)
    l2_buy = float(features.get("l2_buy_vol_2pct") or 0.0)
    l2_sell = float(features.get("l2_sell_vol_2pct") or 0.0)
    bb_width = float(features.get("bb_width_1h") or 0.0)
    vol_ratio = float(features.get("volume_ratio_1h") or 1.0)
    last_price = float(features.get("last_price") or 0.0)
    fib_500 = float(features.get("fib_500") or 0.0)

    # --- Liquidity: $1M = 0.0 (floor), $5M+ = 1.0 (strong) ---
    # Below $1M the labeler already SKIPs, so we normalize relative to the tradeable band.
    if quote_vol >= 5_000_000.0:
        norm["liquidity"] = 1.0
    elif quote_vol >= 1_000_000.0:
        norm["liquidity"] = (quote_vol - 1_000_000.0) / 4_000_000.0  # [0.0, 1.0]
    else:
        norm["liquidity"] = max(-1.0, (quote_vol / 1_000_000.0) - 1.0)  # [-1.0, 0.0]

    if direction == "LONG":
        # Trend: ±5% is a strong day in crypto (not ±10%)
        norm["trend_strength"] = max(-1.0, min(1.0, day_change / 5.0))
        norm["relative_strength"] = (
            max(-1.0, min(1.0, rs_vs_btc_7d / RS_7D_SCALE)) if rs_vs_btc_7d is not None else 0.0
        )

        # Volatility compression: midrange price + tight BBands = coiled spring
        dist_from_mid = abs(pos_in_range - 0.5) * 2  # [0, 1]
        if bb_width > 0:
            compression = max(0.0, 1.0 - (bb_width / 0.08))
            norm["volatility_compression"] = (1.0 - dist_from_mid) * compression * 2.0 - 1.0
        else:
            norm["volatility_compression"] = 0.0  # No BB data → neutral, not penalized

        # Momentum: RSI centered at 50. Oversold for LONGs is bullish signal.
        if rsi_1h > 70.0:
            norm["momentum"] = -0.8  # Overbought penalty (not max -1.0 to allow some upside)
        elif rsi_1h < 30.0:
            norm["momentum"] = 0.8   # Deeply oversold = strong LONG signal
        else:
            # Linear map: RSI 30 → +0.8, RSI 50 → 0.0, RSI 70 → -0.8
            norm["momentum"] = max(-1.0, min(1.0, -(rsi_1h - 50.0) / 25.0))

        # L2 support: 0 → 0.0 (neutral, no data), $100K+ → positive, $500K+ → max
        if l2_buy > 0:
            norm["l2_support"] = min(1.0, l2_buy / 250_000.0)
        else:
            norm["l2_support"] = 0.0  # No L2 data → neutral

        # Confluence signals for interaction bonuses (boolean 0/1)
        norm["rsi_oversold"] = 1.0 if rsi_1h < 40.0 else 0.0
        fib_dist = abs(last_price - fib_500) / fib_500 if fib_500 > 0 else 1.0
        norm["fib_confluence"] = 1.0 if fib_dist < 0.015 else 0.0  # Widened from 1% to 1.5%
        norm["volume_expansion"] = min(1.0, max(0.0, (vol_ratio - 1.0) / 1.0)) if vol_ratio > 1.0 else 0.0
        norm["bb_squeeze"] = 1.0 if 0.0 < bb_width < 0.04 else 0.0  # Widened threshold
        norm["trend_aligned"] = 1.0 if day_change >= -1.0 else 0.0  # Tolerant: slight dips OK

    else:
        # SHORT
        norm["trend_weakness"] = max(-1.0, min(1.0, -day_change / 5.0))
        norm["relative_weakness"] = (
            max(-1.0, min(1.0, -rs_vs_btc_7d / RS_7D_SCALE)) if rs_vs_btc_7d is not None else 0.0
        )

        dist_from_mid = abs(pos_in_range - 0.5) * 2
        if bb_width > 0:
            expansion = min(1.0, bb_width / 0.08)
            norm["volatility_expansion"] = (1.0 - dist_from_mid) * expansion * 2.0 - 1.0
        else:
            norm["volatility_expansion"] = 0.0

        if rsi_1h < 30.0:
            norm["momentum"] = -0.8  # Oversold penalty for shorts
        elif rsi_1h > 70.0:
            norm["momentum"] = 0.8   # Overbought = strong SHORT signal
        else:
            norm["momentum"] = max(-1.0, min(1.0, (rsi_1h - 50.0) / 25.0))

        if l2_sell > 0:
            norm["l2_resistance"] = min(1.0, l2_sell / 250_000.0)
        else:
            norm["l2_resistance"] = 0.0

        # Confluence signals
        norm["rsi_overbought"] = 1.0 if rsi_1h > 60.0 else 0.0  # Lowered from 65 → 60
        fib_dist = abs(last_price - fib_500) / fib_500 if fib_500 > 0 else 1.0
        norm["fib_confluence"] = 1.0 if fib_dist < 0.015 else 0.0
        norm["volume_expansion"] = min(1.0, max(0.0, (vol_ratio - 1.0) / 1.0)) if vol_ratio > 1.0 else 0.0
        # bb_squeeze is a pre-breakout / LONG signal — not applicable to SHORT setups
        norm["trend_aligned"] = 1.0 if day_change <= 1.0 else 0.0

    return norm


def score(
    features: FeatureDict, 
    config: ScoringConfig | None = None,
    trade_direction: str = "LONG",
    regime: str = "TRENDING_UP",
    macro_thrust: float = 0.0,
) -> ScoreBreakdown:
    """Compute composite score [0, 100] from features via weighted interaction.
    
    Returns:
        {
            "baseline": int,
            "components": {component_name: unweighted_norm_value, ...},
            "interactions": float,
            "total": float,
            "clamped": float,
            "funding_rate": float | None,
            "oi_change_pct": float | None,
        }
    """
    if config is None:
        config = ScoringConfig()

    baseline = config.baseline
    norm = normalize_features(features, trade_direction)
    components_dump = {k: round(v, 3) for k, v in norm.items()}

    # Which components this symbol actually has data for, and how much of the
    # model that covers. Computed before the ML branch so both paths report the
    # same shape and the same honesty about what was observed.
    weights = config.component_weights.LONG if trade_direction == "LONG" else config.component_weights.SHORT
    backed = availability(features, trade_direction)
    edge_norm, edge, coverage = edge_and_coverage(norm, weights, backed)

    # 7d relative strength, read here as well as in normalize_features because the
    # interaction bonus below scores the same measure.
    _rs7 = features.get("rs_vs_btc_7d")
    rs_vs_btc_7d = float(_rs7) if _rs7 is not None else None

    # --- Optional XGBoost override (OFF unless enable_ml_scoring is set) ---
    # Deliberately gated: this branch early-returns and bypasses every weight,
    # interaction bonus, regime modifier and options-flow adjustment below.
    model = _get_xgb_model()
    if model is not None:
        import numpy as np
        
        # We process Options features synchronously prior to array compilation
        iv_skew = 0.0
        gamma_wall_proximity = 0.0
        
        from tpt.engine.ws_memory import ws_memory
        pid = features.get("product_id", "")
        if pid and "-" in pid:
            opt = ws_memory.get_macro_options(pid.split("-")[0])
            if opt:
                iv_skew = float(opt.get("iv_skew", 0.0))
                if opt.get("gamma_walls"):
                    gamma_wall_proximity = 0.01
        
        # Build strict 1D native array to bypass heavy Pandas allocations inside asyncio loop
        X = np.array([[
            float(features.get('day_change_pct') or 0.0),
            float(features.get('pos_in_range') or 0.5),
            float(features.get('quote_vol_24h') or 0.0),
            float(features.get('rsi_1h') or 50.0),
            float(features.get('macd_1h') or 0.0),
            float(features.get('rsi_15m') or 50.0),
            float(features.get('bb_width_1h') or 0.05),
            float(features.get('bb_pct_b_1h') or 0.5),
            float(features.get('volume_ratio_1h') or 1.0),
            iv_skew,
            gamma_wall_proximity,
            float(features.get('rs_vs_btc') or 0.0)
        ]])

        # Evaluate Machine Learning Inference
        prob = float(model.predict_proba(X)[0][1])
        clamped = round(prob * 100.0, 2)
        components_dump["xgboost_probability"] = prob
        
        return {
            "baseline": 50,
            "components": components_dump,
            "edge": round(edge, 2),
            "coverage": round(coverage, 3),
            "coverage_band": coverage_band(coverage),
            "rank_key": round(baseline + (clamped - 50.0) * coverage, 2),
            "feature_version": FEATURE_VERSION,
            "interactions": 0.0,
            "total": clamped,
            "clamped": clamped,
            "funding_rate": features.get("funding_rate"),
            "oi_change_pct": features.get("oi_change_pct")
        }
    # --- END XGBoost Override ---
    
    # Evidence-adjusted base.
    #
    # `weights` and `backed` are resolved above. Summing only the backed
    # components and scaling by coverage is arithmetically identical to the
    # historical zero-filled sum (`sum(w_i * x_i) == edge_norm * coverage`), but
    # it is now explicit that a thinly-observed symbol is *shrunk toward neutral*
    # rather than genuinely neutral — and that shrinkage is applied to the
    # interactions too, via `shrink_interactions` below.
    #
    # Interactions are split by origin, because they do not deserve equal trust.
    # Feature interactions are conclusions drawn from this symbol's own data, so
    # they shrink with its coverage. Macro interactions arrive from an independent
    # feed (regime, funding, dealer gamma) and only fire when that feed delivered,
    # so they are already self-gating.
    features_ix = 0.0
    macro_ix = 0.0
    
    # 1. Confluence: Oversold/Overbought at Fib support/resistance
    if (norm.get("rsi_oversold", 0.0) > 0.5 or norm.get("rsi_overbought", 0.0) > 0.5) and norm.get("fib_confluence", 0.0) > 0.5:
        features_ix += config.interaction_bonuses.confluence_bonus
        
    # 2. Breakout: Volume expansion out of a Bollinger squeeze
    if norm.get("volume_expansion", 0.0) > 0.5 and norm.get("bb_squeeze", 0.0) > 0.5:
        features_ix += config.interaction_bonuses.breakout_bonus

    # 3. Regime Modifiers
    # Shorting into TRENDING_UP (or longing into TRENDING_DOWN) fights the macro trend.
    counter_trend = (
        (regime == "TRENDING_UP" and trade_direction == "SHORT")
        or (regime == "TRENDING_DOWN" and trade_direction == "LONG")
    )
    if counter_trend and not norm.get("trend_aligned", 0.0):
        # Fix 2: Hard Trend Veto. Reject totally instead of penalising.
        return {
            "baseline": baseline,
            "components": components_dump,
            "backed": backed,
            "edge": 0.0,
            "coverage": 0.0,
            "coverage_band": "NONE",
            "rank_key": 0.0,
            "feature_version": FEATURE_VERSION,
            "interactions": 0.0,
            "feature_interactions": 0.0,
            "macro_interactions": 0.0,
            "total": 0.0,
            "clamped": 0.0,
            "funding_rate": features.get("funding_rate"),
            "oi_change_pct": features.get("oi_change_pct"),
            "veto": "COUNTER_TREND",
        }

    # 4. Institutional Perpetuals Filter (Over-leveraged Liquidation Squeezes)
    fr = features.get("funding_rate")
    oi = features.get("oi_change_pct")
    
    if fr is not None and oi is not None:
        fr_v = float(fr)
        oi_v = float(oi)
        
        # Long Squeeze condition (Open Interest expanding rapidly with highly positive funding over 0.05%)
        if oi_v > 5.0 and fr_v > 0.0005:
            if trade_direction == "LONG":
                macro_ix -= 20.0
                components_dump["long_squeeze_penalty"] = -20.0
            else:
                macro_ix += 15.0
                components_dump["liquidation_hunt_bonus"] = 15.0
                
        # Short Squeeze condition (High OI with deeply negative funding)
        elif oi_v > 5.0 and fr_v < -0.0005:
            if trade_direction == "LONG":
                macro_ix += 15.0
                components_dump["short_squeeze_bonus"] = 15.0
            else:
                macro_ix -= 20.0
                components_dump["crowded_short_penalty"] = -20.0

    # 5. Options Gamma Flow Resistance/Support (GEX)
    from tpt.engine.ws_memory import ws_memory
    pid = features.get("product_id")
    if pid and "-" in pid:
        underlying = pid.split("-")[0]
        options = ws_memory.get_macro_options(underlying)
        if options:
            gamma_walls = options.get("gamma_walls", [])
            calls = sorted([w["strike"] for w in gamma_walls if w["type"] == "RESISTANCE"])
            puts = sorted([w["strike"] for w in gamma_walls if w["type"] == "SUPPORT"])
            last_p = float(features.get("last_price", 0))

            if trade_direction == "LONG":
                # Trapped tightly under a Call Wall (Negative GEX Resistance)
                closest_call = next((w for w in calls if w > last_p), None)
                if closest_call and (closest_call - last_p) / last_p < 0.015:
                    macro_ix -= 10.0
                    components_dump["gamma_wall_resistance"] = -10.0
                
                # Bouncing off a Put Wall (Positive GEX Support)
                closest_put = next((w for w in reversed(puts) if w < last_p), None)
                if closest_put and (last_p - closest_put) / closest_put < 0.01:
                    macro_ix += 12.0
                    components_dump["gamma_wall_support"] = 12.0

            else: # SHORT
                # Bouncing off a Call Wall (Resistance)
                closest_call = next((w for w in calls if w > last_p), None)
                if closest_call and (closest_call - last_p) / last_p < 0.01:
                    macro_ix += 12.0
                    components_dump["gamma_wall_resistance_bounce"] = 12.0
                
                # Trapped directly above a Put Wall (Support)
                closest_put = next((w for w in reversed(puts) if w < last_p), None)
                if closest_put and (last_p - closest_put) / closest_put < 0.015:
                    macro_ix -= 10.0
                    components_dump["gamma_wall_support"] = -10.0

            # 6. Volatility IV Skew (Fear / Greed Metric)
            # Positive Skew = Puts are higher IV = Fear (Bearish)
            # Negative Skew = Calls are higher IV = Greed (Bullish)
            skew = options.get("iv_skew", 0.0)
            if skew > 0.03: # High Fear (Bearish sentiment)
                if trade_direction == "LONG":
                    macro_ix -= 12.0
                    components_dump["high_put_skew_penalty"] = -12.0
                else: 
                    macro_ix += 8.0
                    components_dump["high_put_skew_bonus"] = 8.0
            elif skew < -0.03: # Extreme Greed (Bullish Sentiment)
                if trade_direction == "LONG":
                    macro_ix += 10.0
                    components_dump["call_skew_greed_bonus"] = 10.0
                else:
                    macro_ix -= 12.0
                    components_dump["call_skew_greed_penalty"] = -12.0

    # 7. Relative Strength (7d vs BTC)
    # Same 7d horizon as the weighted component above. Scoring the same input
    # twice — once as a weighted component and again as a bonus — is what let a
    # candle-blind symbol saturate the top of the scale, so both now read the one
    # independent, multi-horizon measure.
    rs = rs_vs_btc_7d
    if rs is not None and rs > 2.0:
        if trade_direction == "LONG":
            bonus = min(15.0, rs * RS_7D_BONUS_FACTOR)
            features_ix += bonus
            components_dump["rs_btc_bonus"] = bonus
        else:
            penalty = min(15.0, rs * RS_7D_BONUS_FACTOR)
            features_ix -= penalty
            components_dump["rs_btc_short_penalty"] = -penalty
    elif rs is not None and rs < -2.0:
        if trade_direction == "SHORT":
            bonus = min(15.0, abs(rs) * RS_7D_BONUS_FACTOR)
            features_ix += bonus
            components_dump["rs_btc_weakness_bonus"] = bonus
        else:
            penalty = min(15.0, abs(rs) * RS_7D_BONUS_FACTOR)
            features_ix -= penalty
            components_dump["rs_btc_long_penalty"] = -penalty

    # 8. Macro beta headwind — BTC's own push, priced rather than vetoed.
    #
    # This replaces a hard rule in the labeler that returned SKIP for every LONG
    # whenever BTC sat below its short SMA and was down >1.5% on the day. That
    # veto discarded the entire full-coverage cohort — measured on a live scan:
    # 72 of 72 longs skipped, including eleven scoring >=60 and averaging 79.9,
    # among them a symbol up 73% against BTC over seven days. A broad dump is
    # exactly when relative strength is the most informative thing in the book,
    # so the hostility is priced in proportion to its magnitude and an
    # exceptional setup can still clear the entry gate on its own evidence.
    #
    # Macro-sourced, so it is not scaled by the symbol's own coverage.
    headwind = -macro_thrust if trade_direction == "LONG" else macro_thrust
    if headwind > 0.0:
        span = config.macro_beta_full_at_pct
        saturating = min(1.0, headwind / span) if span > 0 else 1.0
        penalty = config.macro_beta_penalty * saturating
        macro_ix -= penalty
        components_dump["macro_beta_headwind"] = round(-penalty, 2)

    # Feature interactions are trusted in proportion to the evidence behind them.
    interactions = shrink_interactions(features_ix, macro_ix, coverage)

    key = rank_key(edge_norm, coverage, interactions, baseline)
    clamped = max(0.0, min(100.0, key))

    funding_rate = features.get("funding_rate")
    oi_change = features.get("oi_change_pct")

    components_dump["coverage"] = round(coverage, 3)

    return {
        "baseline": baseline,
        "components": components_dump,
        # Which components a real observation actually backed. Without this the UI
        # cannot tell a zero-filled `0.0` (no data) from a genuine neutral reading,
        # and would present an unmeasured component as though it had been measured.
        "backed": backed,
        # How good what we saw was ...
        "edge": round(edge, 2),
        # ... and how much of the model we actually got to see.
        "coverage": round(coverage, 3),
        "coverage_band": coverage_band(coverage),
        "rank_key": round(key, 2),
        "feature_version": FEATURE_VERSION,
        "interactions": round(interactions, 2),
        "feature_interactions": round(features_ix, 2),
        "macro_interactions": round(macro_ix, 2),
        "total": round(key, 2),
        "clamped": round(clamped, 2),
        "funding_rate": funding_rate,
        "oi_change_pct": oi_change,
    }

