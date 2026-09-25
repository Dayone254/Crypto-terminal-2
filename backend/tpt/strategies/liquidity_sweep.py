"""LuxAlgo Liquidity Sweep & Stop Hunt Strategy Plugin."""
from __future__ import annotations

from typing import Any

from tpt.strategies.base import BaseStrategy


class LiquiditySweepStrategy(BaseStrategy):
    """LuxAlgo Liquidity Sweep & Stop Hunt strategy plugin.
    
    Detects Equal Highs (EQH) and Equal Lows (EQL) liquidity pools where retail stop losses cluster,
    identifying wick sweeps and immediate range reclaim setups.
    """

    strategy_id: str = "liquidity_sweep"
    name: str = "Liquidity Sweep & Stop Hunt"
    description: str = "Detects Equal Highs (EQH) and Equal Lows (EQL) liquidity sweeps with immediate range reclaims."
    author: str = "TapeRadar Quant Lab"
    version: str = "1.0.0"

    def evaluate_signal(
        self,
        symbol: str,
        candles_15m: list[list[Any]],
        candles_1h: list[list[Any]] | None = None,
        btc_candles_1h: list[list[Any]] | None = None,
    ) -> dict[str, Any] | None:
        bars = candles_15m or candles_1h
        if not bars or len(bars) < 20:
            return None

        # Extract last 20 bars
        window = bars[-20:]
        highs = [float(c[2]) for c in window]
        lows = [float(c[3]) for c in window]
        closes = [float(c[4]) for c in window]

        curr_high = highs[-1]
        curr_low = lows[-1]
        curr_close = closes[-1]

        # ── 1. Detect Equal Lows (EQL) in preceding 18 bars ─────────────────
        prev_lows = lows[:-2]  # Exclude current bar and trigger bar
        eql_level = None
        eql_count = 0

        for i in range(len(prev_lows)):
            for j in range(i + 3, len(prev_lows)):
                l1 = prev_lows[i]
                l2 = prev_lows[j]
                # Lows match within 0.25% tolerance band
                if abs(l1 - l2) / min(l1, l2) <= 0.0025:
                    eql_level = min(l1, l2)
                    eql_count += 1
                    break
            if eql_level:
                break

        # ── 2. Detect Equal Highs (EQH) in preceding 18 bars ────────────────
        prev_highs = highs[:-2]
        eqh_level = None
        eqh_count = 0

        for i in range(len(prev_highs)):
            for j in range(i + 3, len(prev_highs)):
                h1 = prev_highs[i]
                h2 = prev_highs[j]
                # Highs match within 0.25% tolerance band
                if abs(h1 - h2) / max(h1, h2) <= 0.0025:
                    eqh_level = max(h1, h2)
                    eqh_count += 1
                    break
            if eqh_level:
                break

        # ── 3. Bullish Liquidity Sweep (Long Setup) ─────────────────────────
        if eql_level:
            # Current low pierces below EQL level (sweep)
            is_swept = curr_low < eql_level * 0.998
            # Current close reclaims back above EQL level (reclaim)
            is_reclaimed = curr_close > eql_level * 1.0005

            if is_swept and is_reclaimed:
                sweep_depth_pct = (eql_level - curr_low) / eql_level * 100.0
                stop_loss = round(curr_low * 0.997, 4)
                risk = curr_close - stop_loss
                if risk <= 0:
                    return None

                tp1 = round(curr_close + (risk * 2.5), 4)
                tp2 = round(curr_close + (risk * 4.0), 4)
                score = round(72.0 + min(20.0, sweep_depth_pct * 15.0), 1)

                return {
                    "symbol": symbol,
                    "side": "LONG",
                    "label": "ENTRY_ZONE",
                    "composite_score": min(95.0, score),
                    "entry_price": curr_close,
                    "stop_loss": stop_loss,
                    "take_profit_1": tp1,
                    "take_profit_2": tp2,
                    "strategy_id": self.strategy_id,
                    "strategy_name": self.name,
                    "score_breakdown": {
                        "liquidity_type": "EQL_SWEEP",
                        "eql_level": eql_level,
                        "sweep_depth_pct": round(sweep_depth_pct, 2),
                    },
                }

        # ── 4. Bearish Liquidity Sweep (Short Setup) ────────────────────────
        if eqh_level:
            # Current high pierces above EQH level (sweep)
            is_swept = curr_high > eqh_level * 1.002
            # Current close reclaims back below EQH level (reclaim)
            is_reclaimed = curr_close < eqh_level * 0.9995

            if is_swept and is_reclaimed:
                sweep_depth_pct = (curr_high - eqh_level) / eqh_level * 100.0
                stop_loss = round(curr_high * 1.003, 4)
                risk = stop_loss - curr_close
                if risk <= 0:
                    return None

                tp1 = round(curr_close - (risk * 2.5), 4)
                tp2 = round(curr_close - (risk * 4.0), 4)
                score = round(72.0 + min(20.0, sweep_depth_pct * 15.0), 1)

                return {
                    "symbol": symbol,
                    "side": "SHORT",
                    "label": "ENTRY_ZONE",
                    "composite_score": min(95.0, score),
                    "entry_price": curr_close,
                    "stop_loss": stop_loss,
                    "take_profit_1": tp1,
                    "take_profit_2": tp2,
                    "strategy_id": self.strategy_id,
                    "strategy_name": self.name,
                    "score_breakdown": {
                        "liquidity_type": "EQH_SWEEP",
                        "eqh_level": eqh_level,
                        "sweep_depth_pct": round(sweep_depth_pct, 2),
                    },
                }

        return None
