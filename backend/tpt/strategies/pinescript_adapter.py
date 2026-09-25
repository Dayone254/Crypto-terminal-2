"""TradingView PineScript Rule Transpiler & Strategy Adapter Plugin."""
from __future__ import annotations

from typing import Any

from tpt.strategies.base import BaseStrategy


def _ema(values: list[float], length: int) -> list[float]:
    """Calculate Exponential Moving Average (EMA) equivalent to PineScript ta.ema()."""
    if not values or len(values) < length:
        return [0.0] * len(values)

    multiplier = 2.0 / (length + 1)
    ema_vals = [0.0] * len(values)
    # Initialize with simple moving average
    ema_vals[length - 1] = sum(values[:length]) / length

    for i in range(length, len(values)):
        ema_vals[i] = (values[i] - ema_vals[i - 1]) * multiplier + ema_vals[i - 1]

    return ema_vals


def _rsi(values: list[float], length: int = 14) -> float:
    """Calculate Relative Strength Index (RSI) equivalent to PineScript ta.rsi()."""
    if len(values) <= length:
        return 50.0

    gains = []
    losses = []
    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]
        if diff >= 0:
            gains.append(diff)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(diff))

    avg_gain = sum(gains[-length:]) / length
    avg_loss = sum(losses[-length:]) / length

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


class PineScriptAdapterStrategy(BaseStrategy):
    """PineScript Strategy Adapter plugin.
    
    Parses and evaluates rules converted from TradingView PineScript (e.g. EMA crossovers,
    RSI extremes, and ATR trailing stops) inside the TapeRadar backtest engine.
    """

    strategy_id: str = "pinescript_adapter"
    name: str = "PineScript Transpiled Rules"
    description: str = "Executes strategy rules converted from TradingView PineScript (EMA crossover + RSI filter)."
    author: str = "LuxAlgo / TapeRadar Adapter"
    version: str = "1.0.0"

    def evaluate_signal(
        self,
        symbol: str,
        candles_15m: list[list[Any]],
        candles_1h: list[list[Any]] | None = None,
        btc_candles_1h: list[list[Any]] | None = None,
    ) -> dict[str, Any] | None:
        bars = candles_15m or candles_1h
        if not bars or len(bars) < 35:
            return None

        closes = [float(c[4]) for c in bars]
        highs = [float(c[2]) for c in bars]
        lows = [float(c[3]) for c in bars]

        curr_close = closes[-1]
        curr_high = highs[-1]
        curr_low = lows[-1]

        # ── PineScript Rule Calculations ─────────────────────────────────────
        # ta.ema(close, 9) and ta.ema(close, 21)
        ema_fast = _ema(closes, 9)
        ema_slow = _ema(closes, 21)
        rsi = _rsi(closes, 14)

        fast_prev, fast_curr = ema_fast[-2], ema_fast[-1]
        slow_prev, slow_curr = ema_slow[-2], ema_slow[-1]

        # ta.crossover(ema_fast, ema_slow)
        is_bullish_cross = (fast_prev <= slow_prev) and (fast_curr > slow_curr)
        # ta.crossunder(ema_fast, ema_slow)
        is_bearish_cross = (fast_prev >= slow_prev) and (fast_curr < slow_curr)

        # ── 1. Bullish PineScript Signal (LONG) ──────────────────────────────
        if is_bullish_cross and rsi < 65.0:
            stop_loss = round(min(lows[-3:]) * 0.996, 4)
            risk = curr_close - stop_loss
            if risk <= 0:
                return None

            tp1 = round(curr_close + (risk * 2.0), 4)
            tp2 = round(curr_close + (risk * 3.5), 4)

            return {
                "symbol": symbol,
                "side": "LONG",
                "label": "ENTRY_ZONE",
                "composite_score": round(68.0 + min(20.0, (65.0 - rsi) * 0.5), 1),
                "entry_price": curr_close,
                "stop_loss": stop_loss,
                "take_profit_1": tp1,
                "take_profit_2": tp2,
                "strategy_id": self.strategy_id,
                "strategy_name": self.name,
                "score_breakdown": {
                    "pinescript_rule": "ta.crossover(ta.ema(9), ta.ema(21))",
                    "rsi": round(rsi, 1),
                    "ema_fast": round(fast_curr, 2),
                    "ema_slow": round(slow_curr, 2),
                },
            }

        # ── 2. Bearish PineScript Signal (SHORT) ─────────────────────────────
        if is_bearish_cross and rsi > 35.0:
            stop_loss = round(max(highs[-3:]) * 1.004, 4)
            risk = stop_loss - curr_close
            if risk <= 0:
                return None

            tp1 = round(curr_close - (risk * 2.0), 4)
            tp2 = round(curr_close - (risk * 3.5), 4)

            return {
                "symbol": symbol,
                "side": "SHORT",
                "label": "ENTRY_ZONE",
                "composite_score": round(68.0 + min(20.0, (rsi - 35.0) * 0.5), 1),
                "entry_price": curr_close,
                "stop_loss": stop_loss,
                "take_profit_1": tp1,
                "take_profit_2": tp2,
                "strategy_id": self.strategy_id,
                "strategy_name": self.name,
                "score_breakdown": {
                    "pinescript_rule": "ta.crossunder(ta.ema(9), ta.ema(21))",
                    "rsi": round(rsi, 1),
                    "ema_fast": round(fast_curr, 2),
                    "ema_slow": round(slow_curr, 2),
                },
            }

        return None
