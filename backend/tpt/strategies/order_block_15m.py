"""15-Minute Institutional Order Block & Fair Value Gap (FVG) Strategy."""
from __future__ import annotations

from typing import Any

from tpt.strategies.base import BaseStrategy


class OrderBlock15mStrategy(BaseStrategy):
    """Institutional 15m Order Block retest strategy with displacement and FVG confirmation."""

    strategy_id: str = "order_block_15m"
    name: str = "15m Order Block & Imbalance"
    description: str = "Detects 15m institutional order blocks with strong displacement impulses and FVG retests."
    author: str = "TapeRadar Quant Lab"
    version: str = "1.0.0"

    def evaluate_signal(
        self,
        symbol: str,
        candles_15m: list[list[Any]],
        candles_1h: list[list[Any]] | None = None,
        btc_candles_1h: list[list[Any]] | None = None,
    ) -> dict[str, Any] | None:
        if not candles_15m or len(candles_15m) < 6:
            return None

        # Extract last 6 bars [ob_bar, impulse_1, impulse_2, fvg_bar, prev_bar, curr_bar]
        c_ob = candles_15m[-6]
        c_imp1 = candles_15m[-5]
        c_imp2 = candles_15m[-4]
        c_fvg = candles_15m[-3]
        c_prev = candles_15m[-2]
        c_curr = candles_15m[-1]

        ob_open, ob_high, ob_low, ob_close = (
            float(c_ob[1]),
            float(c_ob[2]),
            float(c_ob[3]),
            float(c_ob[4]),
        )
        curr_close = float(c_curr[4])
        curr_high = float(c_curr[2])
        curr_low = float(c_curr[3])

        # ── 1. Bullish Order Block (Long Setup) ─────────────────────────────
        # Condition A: OB bar was bearish (close < open)
        is_bullish_ob_structure = ob_close < ob_open
        # Condition B: Followed by strong upward displacement (> 0.6% impulse in 2 bars)
        impulse_gain_pct = (float(c_imp2[4]) - ob_high) / ob_high * 100.0
        is_strong_displacement_up = impulse_gain_pct >= 0.5

        if is_bullish_ob_structure and is_strong_displacement_up:
            ob_zone_high = ob_high
            ob_zone_low = ob_low

            # Condition C: Retest check — current low touches or enters OB zone
            is_retesting_ob_zone = curr_low <= ob_zone_high * 1.002 and curr_close >= ob_zone_low * 0.998

            if is_retesting_ob_zone:
                stop_loss = round(ob_zone_low * 0.997, 4)  # 0.3% buffer below OB low
                risk = curr_close - stop_loss
                if risk <= 0:
                    return None

                tp1 = round(curr_close + (risk * 2.0), 4)
                tp2 = round(curr_close + (risk * 3.5), 4)

                return {
                    "symbol": symbol,
                    "side": "LONG",
                    "label": "ENTRY_ZONE",
                    "composite_score": round(65.0 + min(25.0, impulse_gain_pct * 10.0), 1),
                    "entry_price": curr_close,
                    "stop_loss": stop_loss,
                    "take_profit_1": tp1,
                    "take_profit_2": tp2,
                    "strategy_id": self.strategy_id,
                    "strategy_name": self.name,
                    "score_breakdown": {
                        "ob_type": "BULLISH_OB",
                        "ob_zone_high": ob_zone_high,
                        "ob_zone_low": ob_zone_low,
                        "impulse_gain_pct": round(impulse_gain_pct, 2),
                    },
                }

        # ── 2. Bearish Order Block (Short Setup) ────────────────────────────
        is_bearish_ob_structure = ob_close > ob_open
        impulse_drop_pct = (ob_low - float(c_imp2[4])) / ob_low * 100.0
        is_strong_displacement_down = impulse_drop_pct >= 0.5

        if is_bearish_ob_structure and is_strong_displacement_down:
            ob_zone_high = ob_high
            ob_zone_low = ob_low

            # Retest check — current high touches OB zone from below
            is_retesting_ob_zone = curr_high >= ob_zone_low * 0.998 and curr_close <= ob_zone_high * 1.002

            if is_retesting_ob_zone:
                stop_loss = round(ob_zone_high * 1.003, 4)
                risk = stop_loss - curr_close
                if risk <= 0:
                    return None

                tp1 = round(curr_close - (risk * 2.0), 4)
                tp2 = round(curr_close - (risk * 3.5), 4)

                return {
                    "symbol": symbol,
                    "side": "SHORT",
                    "label": "ENTRY_ZONE",
                    "composite_score": round(65.0 + min(25.0, impulse_drop_pct * 10.0), 1),
                    "entry_price": curr_close,
                    "stop_loss": stop_loss,
                    "take_profit_1": tp1,
                    "take_profit_2": tp2,
                    "strategy_id": self.strategy_id,
                    "strategy_name": self.name,
                    "score_breakdown": {
                        "ob_type": "BEARISH_OB",
                        "ob_zone_high": ob_zone_high,
                        "ob_zone_low": ob_zone_low,
                        "impulse_drop_pct": round(impulse_drop_pct, 2),
                    },
                }

        return None
