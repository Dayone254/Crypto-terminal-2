"""Market regime detection engine.

Classifies the overarching market microstructure into discrete regimes based on
the network's primary asset (typically BTC).
"""
from __future__ import annotations

from typing import Literal

from tpt.engine.features import FeatureDict

Regime = Literal["TRENDING_UP", "TRENDING_DOWN", "RANGING", "VOLATILE"]


def detect_regime(btc_features: FeatureDict) -> Regime:
    """Classify the current market regime based on BTC features.
    
    Args:
        btc_features: The output of compute_features() for BTC-USD.
        
    Returns:
        The detected Regime classification.
    """
    rsi_6h = btc_features.get("rsi_6h")
    ema_trend = btc_features.get("ema_trend_6h")
    bb_width = btc_features.get("bb_width_1h")
    day_change = btc_features.get("day_change_pct") or 0.0

    # Fallbacks if multi-timeframe data is missing
    if rsi_6h is None:
        rsi_6h = 50.0
    if ema_trend is None:
        ema_trend = (day_change > 0)
    if bb_width is None:
        # Conservative fallback: treat unknown volatility as RANGING so we don’t
        # allow live trades through a TRENDING fast-path when candle data is missing.
        import logging
        logging.getLogger(__name__).warning(
            "detect_regime: bb_width is None (1h candle fetch may have failed) — defaulting regime to RANGING"
        )
        return "RANGING"

    # 1. Volatility / Breakout States
    # If BB width is very wide (e.g., > 6% on 1h for BTC) or day change is extreme
    if bb_width > 0.06 or abs(day_change) > 8.0:
        return "VOLATILE"

    # 2. Ranging / Compression States
    # (Bollinger Bands tightly compressed or 6h RSI dead flat)
    if bb_width < 0.015 or (45.0 <= rsi_6h <= 55.0 and abs(day_change) < 1.0):
        return "RANGING"

    # 3. Trending States
    # Up: Above 6h EMA(50), 6h RSI > 50, and generally positive day change
    if ema_trend and rsi_6h > 50.0 and day_change > -1.0:
        return "TRENDING_UP"
        
    # Down: Below 6h EMA(50), 6h RSI < 50, and generally negative day change
    if not ema_trend and rsi_6h < 50.0 and day_change < 1.0:
        return "TRENDING_DOWN"

    # 4. Default Fallback
    if day_change > 0:
        return "TRENDING_UP"
    else:
        return "TRENDING_DOWN"
