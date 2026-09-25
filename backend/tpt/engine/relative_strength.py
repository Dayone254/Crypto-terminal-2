"""
Relative Strength & BTC Regime Signal Engine.

Combines real-time BTC Gamma Engine metrics (Net GEX, Gamma Flip, Dealer Delta)
with Universe-wide Altcoin performance Z-scores to classify high-probability
LONG Leaders and SHORT Laggards.
"""
from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger("tpt.engine.relative_strength")


def calculate_btc_regime(spot_price: float, gamma_data: dict[str, Any]) -> dict[str, Any]:
    """
    Evaluates BTC's Gamma Engine parameters to classify market macro regime.
    
    Returns:
        {
            "regime": "RISK_ON" | "RISK_OFF" | "NEUTRAL",
            "score": float (-100 to +100),
            "reason": str,
            "net_gex_millions": float,
            "gamma_flip_dist_pct": float
        }
    """
    if not gamma_data:
        return {
            "regime": "NEUTRAL",
            "score": 0.0,
            "reason": "No BTC Gamma Engine Data",
            "net_gex_millions": 0.0,
            "gamma_flip_dist_pct": 0.0
        }

    net_gex = float(gamma_data.get("total_net_gex_millions", 0.0) or 0.0)
    flip_level = float(gamma_data.get("gamma_flip", 0.0) or 0.0)
    call_wall = float(gamma_data.get("call_wall", 0.0) or 0.0)
    put_wall = float(gamma_data.get("put_wall", 0.0) or 0.0)

    # 1. Flip Distance %
    flip_dist_pct = 0.0
    if flip_level > 0 and spot_price > 0:
        flip_dist_pct = ((spot_price - flip_level) / spot_price) * 100.0

    # 2. Score Calculation (-100 to +100)
    # GEX Component: +10 per $1B Net GEX (capped at +-50)
    gex_component = max(-50.0, min(50.0, (net_gex / 1000.0) * 10.0))

    # Position Component: +30 if spot above flip, -30 if below
    position_component = 30.0 if spot_price >= flip_level else -30.0

    total_score = max(-100.0, min(100.0, gex_component + position_component))

    # 3. Regime Classification
    if total_score >= 20.0:
        regime = "RISK_ON"
        reason = f"BTC Long Gamma (+${net_gex/1000.0:.1f}B GEX) & Above Flip Level (${flip_level:,.0f})"
    elif total_score <= -20.0:
        regime = "RISK_OFF"
        reason = f"BTC Short Gamma (-${abs(net_gex)/1000.0:.1f}B GEX) & Below Flip Level (${flip_level:,.0f})"
    else:
        regime = "NEUTRAL"
        reason = "BTC Net Gamma in Compression / Transition Range"

    return {
        "regime": regime,
        "score": round(total_score, 1),
        "reason": reason,
        "net_gex_millions": net_gex,
        "gamma_flip_dist_pct": round(flip_dist_pct, 2)
    }


def compute_relative_strength_matrix(
    candidates: list[dict[str, Any]], 
    btc_regime_info: dict[str, Any],
    btc_pairs_cache: dict[str, dict[str, float]]
) -> list[dict[str, Any]]:
    """
    Computes Relative Strength Z-Scores across all universe symbols vs BTC
    and generates actionable trade classifications.
    """
    if not candidates:
        return []

    # Find BTC 24h change for reference fallback
    btc_change = 0.0
    for c in candidates:
        if "BTC" in c.get("product_id", "").upper():
            btc_change = float(c.get("day_change_pct", 0.0) or 0.0)
            break

    # Calculate raw RS = Blended 7D/30D BTC pairs, or fallback to USD diff
    rs_values: list[float] = []
    candidates_with_rs: list[dict[str, Any]] = []

    for c in candidates:
        c_copy = dict(c)
        pid = c_copy.get("product_id", "")
        base_asset = pid.split("-")[0].upper()
        
        # Pull native BTC pair performance if available (e.g. ETH from ETHBTC)
        pair_data = btc_pairs_cache.get(base_asset)
        
        if base_asset == "BTC":
            rs_raw = 0.0
        elif pair_data:
            # institutional blending: 70% 7D strength, 30% 30D strength
            rs_raw = (pair_data.get("7d_pct", 0.0) * 0.7) + (pair_data.get("30d_pct", 0.0) * 0.3)
        else:
            # Fallback to noisy 24h delta if Binance data missing for this symbol
            day_chg = float(c_copy.get("day_change_pct", 0.0) or 0.0)
            rs_raw = day_chg - btc_change

        c_copy["rs_raw"] = round(rs_raw, 2)
        
        if base_asset != "BTC":
            rs_values.append(rs_raw)
            
        candidates_with_rs.append(c_copy)

    # Calculate Mean & Standard Deviation of Altcoins only
    n = len(rs_values)
    if n < 2:
        # Default z-scores to 0 if not enough data
        for c in candidates_with_rs:
            c["rs_z_score"] = 0.0
            base_asset = c.get("product_id", "").split("-")[0].upper()
            if base_asset == "BTC":
                c["rs_signal"] = "BENCHMARK"
                c["rs_signal_label"] = "BTC Benchmark"
            else:
                c["rs_signal"] = "IN_LINE"
                c["rs_signal_label"] = "⚪ Market Performing"
        return candidates_with_rs

    mean_rs = sum(rs_values) / n
    variance = sum((x - mean_rs) ** 2 for x in rs_values) / (n - 1)
    std_rs = math.sqrt(variance) if variance > 0 else 1.0

    btc_regime = btc_regime_info.get("regime", "NEUTRAL")

    # Compute Z-score & Trade Signal Classification
    for c in candidates_with_rs:
        base_asset = c.get("product_id", "").split("-")[0].upper()
        if base_asset == "BTC":
            c["rs_z_score"] = 0.0
            c["rs_signal"] = "BENCHMARK"
            c["rs_signal_label"] = "BTC Benchmark"
            continue
            
        rs_raw = c["rs_raw"]
        z_score = (rs_raw - mean_rs) / std_rs if std_rs > 0 else 0.0
        c["rs_z_score"] = round(z_score, 2)

        # Classification Rules
        if z_score >= 1.2:
            if btc_regime == "RISK_ON":
                c["rs_signal"] = "LONG_LEADER"
                c["rs_signal_label"] = "🟢 LONG Leader (High Beta)"
            else:
                c["rs_signal"] = "OUTPERFORMER"
                c["rs_signal_label"] = "⚡ Outperformer (Solitary Bid)"
        elif z_score <= -1.2:
            if btc_regime == "RISK_ON":
                c["rs_signal"] = "DIVERGENT_SHORT"
                c["rs_signal_label"] = "🔴 SHORT Divergence (Weak in Rally)"
            elif btc_regime == "RISK_OFF":
                c["rs_signal"] = "SHORT_LAGGARD"
                c["rs_signal_label"] = "🔴 SHORT Laggard (Accelerated Fall)"
            else:
                c["rs_signal"] = "UNDERPERFORMER"
                c["rs_signal_label"] = "📉 Underperformer"
        else:
            c["rs_signal"] = "IN_LINE"
            c["rs_signal_label"] = "⚪ Market Performing"

    # Sort candidates by Z-Score descending (Leaders first)
    candidates_with_rs.sort(key=lambda x: x.get("rs_z_score", 0.0), reverse=True)
    return candidates_with_rs
