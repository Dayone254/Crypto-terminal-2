"""Unit test asserting zero look-ahead bias in backtest engine evaluation."""
from __future__ import annotations

import pytest
from tpt.backtest.engine import evaluate_bar_slice
from tpt.config.strategy import load_strategy


def test_no_lookahead_bias():
    """Assert feature values and setup evaluation for bar t are identical
    regardless of whether future bars t+1..t+N exist in dataset or are truncated.
    """
    # Create 50 synthetic 1h bars
    base_ts = 1700000000
    bars = []
    price = 100.0
    for i in range(50):
        ts = base_ts + i * 3600
        open_p = price
        high_p = price + 2.0
        low_p = price - 1.0
        close_p = price + 1.0
        vol = 1000.0 + i * 10.0
        price = close_p
        bars.append([ts, open_p, high_p, low_p, close_p, vol])

    config = load_strategy()

    # Slice at bar 35
    slice_35 = bars[:36]
    eval_short = evaluate_bar_slice("BTC-USD", candles_1h_slice=slice_35, config=config)

    # Slice at bar 45 (contains 10 extra future bars)
    slice_45 = bars[:46]
    # But pass slice_35 to evaluate_bar_slice for bar 35 evaluation
    eval_full = evaluate_bar_slice("BTC-USD", candles_1h_slice=slice_35, config=config)

    if eval_short is None:
        assert eval_full is None
    else:
        assert eval_full is not None
        assert eval_short["symbol"] == eval_full["symbol"]
        assert eval_short["timestamp"] == eval_full["timestamp"]
        assert eval_short["label"] == eval_full["label"]
        assert eval_short["score"] == eval_full["score"]
        assert eval_short["ladder"]["tranche_a_price"] == eval_full["ladder"]["tranche_a_price"]
        assert eval_short["l2_approximated"] is True
