"""Backtest engine — historical bar replay reusing live engine logic without look-ahead bias."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from tpt.config.strategy import StrategyConfig, load_strategy
from tpt.engine.features import compute_features, multi_horizon_returns
from tpt.engine.labeler import compute_tags, label
from tpt.engine.ladder import compute_ladder, sanitize_ladder_dict
from tpt.engine.regime import detect_regime, macro_thrust
from tpt.engine.scorer import score

logger = logging.getLogger(__name__)


@dataclass
class BacktestTradeResult:
    signal_id: str
    symbol: str
    timestamp: int
    trade_direction: str
    label: str
    score: float
    entry_price: float
    stop_price: float
    target_1_price: float
    target_2_price: float
    status: str  # WIN | LOSS | BREAK_EVEN | PARTIAL_WIN | EXPIRED
    realized_r: float
    mfe_r: float
    mae_r: float
    bars_held: int
    l2_approximated: bool = True


from tpt.strategies.base import BaseStrategy

def evaluate_bar_slice(
    symbol: str,
    candles_1h_slice: list[list[Any]],
    candles_1d_slice: list[list[Any]] | None = None,
    candles_15m_slice: list[list[Any]] | None = None,
    candles_6h_slice: list[list[Any]] | None = None,
    btc_1h_slice: list[list[Any]] | None = None,
    btc_1d_slice: list[list[Any]] | None = None,
    config: StrategyConfig | None = None,
    strategy: BaseStrategy | None = None,
) -> dict[str, Any] | None:
    """Evaluate signal generation for a single historical bar slice.
    
    STRICT ZERO LOOK-AHEAD: All candle arrays MUST be sliced up to the current timestamp t.
    Supports either standard TapeRadar composite scoring or pluggable BaseStrategy instances.
    """
    if strategy is not None:
        sig = strategy.evaluate_signal(
            symbol=symbol,
            candles_15m=candles_15m_slice or candles_1h_slice,
            candles_1h=candles_1h_slice,
            btc_candles_1h=btc_1h_slice,
        )
        if not sig:
            return None

        trade_dir = sig.get("trade_direction") or sig.get("side", "LONG")
        entry_p = float(sig.get("entry_price") or (candles_1h_slice[-1][4] if candles_1h_slice else 0.0))
        stop_p = float(sig.get("stop_loss") or (entry_p * 0.98 if trade_dir == "LONG" else entry_p * 1.02))
        tp1_p = float(sig.get("take_profit_1") or (entry_p * 1.04 if trade_dir == "LONG" else entry_p * 0.96))
        tp2_p = float(sig.get("take_profit_2") or tp1_p)
        score_val = float(sig.get("composite_score") or sig.get("score") or 65.0)

        ladder_obj = sig.get("ladder") or {
            "tranche_a_price": entry_p,
            "stop_price": stop_p,
            "target_1_price": tp1_p,
            "target_2_price": tp2_p,
        }

        timestamp_val = int(candles_15m_slice[-1][0]) if candles_15m_slice else (int(candles_1h_slice[-1][0]) if candles_1h_slice else 0)

        return {
            "symbol": symbol,
            "timestamp": timestamp_val,
            "label": sig.get("label", "ENTRY_ZONE"),
            "trade_direction": trade_dir,
            "score": score_val,
            "score_dict": {"clamped": score_val},
            "tags": [sig.get("strategy_name", strategy.name)],
            "ladder": ladder_obj,
            "l2_approximated": True,
            "strategy_id": strategy.strategy_id,
        }

    if not candles_1h_slice or len(candles_1h_slice) < 10:
        return None

    # Cap slice length to 168 bars (1 week) to prevent high slice copying overhead
    if len(candles_1h_slice) > 168:
        candles_1h_slice = candles_1h_slice[-168:]
    if btc_1h_slice and len(btc_1h_slice) > 168:
        btc_1h_slice = btc_1h_slice[-168:]

    if config is None:
        config = load_strategy()

    latest_bar = candles_1h_slice[-1]
    # format: [timestamp, open, high, low, close, volume]
    last_price = float(latest_bar[4])

    # BTC returns & day change for macro thrust
    btc_day_change: float | None = None
    btc_returns: dict[str, float] = {}

    if btc_1h_slice and len(btc_1h_slice) >= 24:
        btc_returns = {
            k: v
            for k, v in multi_horizon_returns(btc_1h_slice, btc_1d_slice).items()
            if v is not None
        }
        b_close = float(btc_1h_slice[-1][4])
        b_open_24h = float(btc_1h_slice[-24][4])
        if b_open_24h > 0:
            btc_day_change = ((b_close - b_open_24h) / b_open_24h) * 100.0

    raw_stats = {
        "last": last_price,
        "open": float(candles_1h_slice[-24][4]) if len(candles_1h_slice) >= 24 else last_price,
        "high": max(float(c[2]) for c in candles_1h_slice[-24:]),
        "low": min(float(c[3]) for c in candles_1h_slice[-24:]),
        "volume": sum(float(c[5]) for c in candles_1h_slice[-24:]),
    }

    feats = compute_features(
        raw_stats=raw_stats,
        raw_ticker=raw_stats,
        raw_candles_1h=candles_1h_slice,
        raw_candles_1d=candles_1d_slice,
        btc_day_change_pct=btc_day_change,
        raw_candles_15m=candles_15m_slice,
        raw_candles_6h=candles_6h_slice,
        btc_returns=btc_returns,
    )
    feats["product_id"] = symbol

    regime = "TRENDING_UP"
    if btc_1h_slice:
        btc_feats = compute_features(
            raw_stats={"last": float(btc_1h_slice[-1][4])},
            raw_ticker={},
            raw_candles_1h=btc_1h_slice,
            raw_candles_1d=btc_1d_slice,
        )
        try:
            regime = detect_regime(btc_feats)
        except Exception:
            pass

    btc_closes_1h = [float(c[4]) for c in btc_1h_slice] if btc_1h_slice else None
    thrust = macro_thrust(btc_closes_1h, btc_day_change)

    long_score = score(feats, config.scoring, trade_direction="LONG", regime=regime, macro_thrust=thrust)
    short_score = score(feats, config.scoring, trade_direction="SHORT", regime=regime, macro_thrust=thrust)

    day_chg = float(feats.get("day_change_pct") or 0.0)
    is_short_allowed = not (day_chg > 3.0 and (short_score["clamped"] - long_score["clamped"]) < 20.0)

    if is_short_allowed and short_score["clamped"] > long_score["clamped"]:
        trade_direction = "SHORT"
        score_dict = short_score
    else:
        trade_direction = "LONG"
        score_dict = long_score

    comp_score = score_dict["clamped"]
    lbl = label(feats, comp_score, config.labeling, trade_direction=trade_direction, regime=regime)
    tags = compute_tags(feats)

    # Pure ATR stop fallback for historical backtest (L2 approximated)
    ladder_dict = compute_ladder(
        product_id=symbol,
        features=feats,
        lbl=lbl,
        composite_score=comp_score,
        config=config.ladder,
        trade_direction=trade_direction,
        regime=regime,
    )

    if not ladder_dict or lbl in ("SKIP", "CHASE"):
        return None

    san = sanitize_ladder_dict(ladder_dict)
    if not san or not san.get("tranche_a_price"):
        return None

    return {
        "symbol": symbol,
        "timestamp": int(latest_bar[0]),
        "label": lbl,
        "trade_direction": trade_direction,
        "score": comp_score,
        "score_dict": score_dict,
        "tags": tags,
        "ladder": san,
        "l2_approximated": True,
    }


def simulate_trade_execution(
    setup: dict[str, Any],
    future_candles_1h: list[list[Any]],
    max_hold_bars: int = 72,
) -> BacktestTradeResult | None:
    """Simulate execution of a generated backtest setup against subsequent 1h bars."""
    ladder = setup["ladder"]
    direction = setup["trade_direction"]
    entry = float(ladder["tranche_a_price"])
    stop = float(ladder["stop_price"])
    tp1 = float(ladder["target_1_price"])
    tp2 = float(ladder.get("target_2_price") or tp1)

    risk = abs(entry - stop)
    if risk <= 0:
        return None

    mfe = 0.0
    mae = 0.0
    bars = 0
    status = "EXPIRED"
    realized_r = 0.0

    for bar in future_candles_1h[:max_hold_bars]:
        bars += 1
        high = float(bar[2])
        low = float(bar[3])

        if direction == "LONG":
            fav = high - entry
            unfav = entry - low
            if fav > mfe:
                mfe = fav
            if unfav > mae:
                mae = unfav

            # Check stop loss
            if low <= stop:
                status = "LOSS"
                realized_r = -1.0
                break
            # Check TP2
            elif high >= tp2:
                status = "WIN"
                realized_r = abs(tp2 - entry) / risk
                break
            # Check TP1
            elif high >= tp1:
                status = "PARTIAL_WIN"
                realized_r = abs(tp1 - entry) / risk
                # Stop moves to breakeven
                stop = entry
        else:  # SHORT
            fav = entry - low
            unfav = high - entry
            if fav > mfe:
                mfe = fav
            if unfav > mae:
                mae = unfav

            # Check stop loss
            if high >= stop:
                status = "LOSS"
                realized_r = -1.0
                break
            # Check TP2
            elif low <= tp2:
                status = "WIN"
                realized_r = abs(entry - tp2) / risk
                break
            # Check TP1
            elif low <= tp1:
                status = "PARTIAL_WIN"
                realized_r = abs(entry - tp1) / risk
                stop = entry

    mfe_r = round(mfe / risk, 2) if risk > 0 else 0.0
    mae_r = round(mae / risk, 2) if risk > 0 else 0.0

    if status == "EXPIRED":
        final_close = float(future_candles_1h[min(bars - 1, len(future_candles_1h) - 1)][4]) if future_candles_1h else entry
        if direction == "LONG":
            realized_r = (final_close - entry) / risk
        else:
            realized_r = (entry - final_close) / risk
        if realized_r > 0:
            status = "PARTIAL_WIN"
        elif realized_r < -0.5:
            status = "LOSS"
        else:
            status = "BREAK_EVEN"

    return BacktestTradeResult(
        signal_id=f"{setup['symbol']}_{setup['timestamp']}",
        symbol=setup["symbol"],
        timestamp=setup["timestamp"],
        trade_direction=direction,
        label=setup["label"],
        score=setup["score"],
        entry_price=entry,
        stop_price=stop,
        target_1_price=tp1,
        target_2_price=tp2,
        status=status,
        realized_r=round(realized_r, 2),
        mfe_r=mfe_r,
        mae_r=mae_r,
        bars_held=bars,
        l2_approximated=True,
    )
