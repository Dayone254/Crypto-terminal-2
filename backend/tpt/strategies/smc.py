"""LuxAlgo Smart Money Concepts (SMC) Strategy Plugin."""
from __future__ import annotations

from typing import Any

from tpt.strategies.base import BaseStrategy


class SmartMoneyConceptsStrategy(BaseStrategy):
    """LuxAlgo Smart Money Concepts (SMC) strategy plugin.
    
    Evaluates institutional market structure (BOS & CHoCH), Order Block zones,
    and Premium/Discount pricing equilibrium.
    """

    strategy_id: str = "smc_institutional"
    name: str = "Smart Money Concepts (SMC)"
    description: str = "Institutional SMC strategy combining BOS, CHoCH, Order Blocks, and Premium/Discount range filtering."
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
        if not bars or len(bars) < 30:
            return None

        # Extract last 30 bars [timestamp, open, high, low, close, volume]
        window = bars[-30:]
        closes = [float(c[4]) for c in window]
        highs = [float(c[2]) for c in window]
        lows = [float(c[3]) for c in window]

        curr_close = closes[-1]
        curr_high = highs[-1]
        curr_low = lows[-1]

        # ── 1. Calculate Swing Range & Equilibrium (Premium vs Discount) ─────
        range_high = max(highs[:-1])
        range_low = min(lows[:-1])
        equilibrium = (range_high + range_low) / 2.0
        range_size = range_high - range_low

        if range_size <= 0:
            return None

        # Position in range (0.0 = low, 1.0 = high)
        range_position = (curr_close - range_low) / range_size
        is_discount = range_position < 0.50  # Valid for LONGS
        is_premium = range_position > 0.50   # Valid for SHORTS

        # ── 2. Identify Swing Pivots for Market Structure ─────────────────────
        # Find local pivot highs and pivot lows in previous bars
        pivot_highs = []
        pivot_lows = []

        for i in range(2, len(window) - 2):
            if highs[i] > highs[i - 1] and highs[i] > highs[i - 2] and highs[i] > highs[i + 1] and highs[i] > highs[i + 2]:
                pivot_highs.append((i, highs[i]))
            if lows[i] < lows[i - 1] and lows[i] < lows[i - 2] and lows[i] < lows[i + 1] and lows[i] < lows[i + 2]:
                pivot_lows.append((i, lows[i]))

        recent_pivot_high = pivot_highs[-1][1] if pivot_highs else range_high
        recent_pivot_low = pivot_lows[-1][1] if pivot_lows else range_low

        # ── 3. Market Structure Signals (BOS / CHoCH) ─────────────────────────
        # Bullish Structure Break: Current close breaks recent pivot high
        is_bullish_break = curr_close > recent_pivot_high
        # Bearish Structure Break: Current close breaks recent pivot low
        is_bearish_break = curr_close < recent_pivot_low

        # ── 4. Evaluate Bullish SMC Setup (LONG) ──────────────────────────────
        if is_bullish_break and is_discount:
            stop_loss = round(min(recent_pivot_low, curr_low * 0.997), 4)
            risk = curr_close - stop_loss
            if risk <= 0:
                return None

            tp1 = round(curr_close + (risk * 2.0), 4)
            tp2 = round(curr_close + (risk * 3.5), 4)

            structure_type = "BULLISH_CHoCH" if curr_close > range_high * 0.99 else "BULLISH_BOS"
            composite_score = round(70.0 + (0.5 - range_position) * 30.0, 1)

            return {
                "symbol": symbol,
                "side": "LONG",
                "label": "ENTRY_ZONE",
                "composite_score": min(95.0, max(60.0, composite_score)),
                "entry_price": curr_close,
                "stop_loss": stop_loss,
                "take_profit_1": tp1,
                "take_profit_2": tp2,
                "strategy_id": self.strategy_id,
                "strategy_name": self.name,
                "score_breakdown": {
                    "structure": structure_type,
                    "zone": "DISCOUNT",
                    "range_position_pct": round(range_position * 100.0, 1),
                    "pivot_high": recent_pivot_high,
                    "pivot_low": recent_pivot_low,
                },
            }

        # ── 5. Evaluate Bearish SMC Setup (SHORT) ─────────────────────────────
        if is_bearish_break and is_premium:
            stop_loss = round(max(recent_pivot_high, curr_high * 1.003), 4)
            risk = stop_loss - curr_close
            if risk <= 0:
                return None

            tp1 = round(curr_close - (risk * 2.0), 4)
            tp2 = round(curr_close - (risk * 3.5), 4)

            structure_type = "BEARISH_CHoCH" if curr_close < range_low * 1.01 else "BEARISH_BOS"
            composite_score = round(70.0 + (range_position - 0.5) * 30.0, 1)

            return {
                "symbol": symbol,
                "side": "SHORT",
                "label": "ENTRY_ZONE",
                "composite_score": min(95.0, max(60.0, composite_score)),
                "entry_price": curr_close,
                "stop_loss": stop_loss,
                "take_profit_1": tp1,
                "take_profit_2": tp2,
                "strategy_id": self.strategy_id,
                "strategy_name": self.name,
                "score_breakdown": {
                    "structure": structure_type,
                    "zone": "PREMIUM",
                    "range_position_pct": round(range_position * 100.0, 1),
                    "pivot_high": recent_pivot_high,
                    "pivot_low": recent_pivot_low,
                },
            }

        return None
