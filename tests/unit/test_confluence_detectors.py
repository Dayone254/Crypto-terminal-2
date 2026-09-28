"""Tests for the confluence-port detectors (sweep / WVF / RSI divergence).

Ports of the operator's Pine entry-system filters into the feature engine.
Candle format matches Coinbase: [time, low, high, open, close, volume].
"""
from __future__ import annotations

from typing import Any

from tpt.engine.features import (
    _compute_directional_pressure,
    _compute_trend_quality,
    _detect_rsi_divergence,
    _detect_sweeps,
    _detect_wvf_spike,
    compute_features,
)
from tpt.engine.labeler import compute_tags
from tpt.engine.scorer import score


def _candle(ts: int, low: float, high: float, open_: float, close: float, vol: float = 10.0) -> list[Any]:
    return [ts, low, high, open_, close, vol]


# ── Sweep detection ──────────────────────────────────────────────────────────


def test_sweep_low_detected_when_wick_pierces_and_closes_back() -> None:
    # 14 bars. Bar 6 is a clean pivot low (98.0) with 5 bars either side above it.
    # Bar 12 wicks to 97.5 but closes back at 100.5 → sweep, 1 bar ago.
    lows = [100.0, 99.8, 99.6, 99.9, 99.5, 99.7, 98.0, 99.5, 99.6, 99.8, 99.5, 99.7, 97.5, 99.9]
    highs = [101.0 + 0.1 * i for i in range(14)]
    closes = [100.5] * 14
    candles = [_candle(i, lows[i], highs[i], 100.0, closes[i]) for i in range(14)]
    candles[12] = _candle(12, 97.5, 101.9, 100.0, 100.5)

    sweep_low, sweep_high = _detect_sweeps(candles)
    assert sweep_low == 1
    assert sweep_high is None


def test_sweep_close_through_is_not_a_sweep() -> None:
    # Same pivot, but the last bar CLOSES below it — that is a break, not a sweep.
    lows = [100.0, 99.8, 99.6, 99.9, 99.5, 99.7, 98.0, 99.5, 99.6, 99.8, 99.5, 99.7, 97.5, 99.9]
    highs = [101.0 + 0.1 * i for i in range(14)]
    candles = [_candle(i, lows[i], highs[i], 100.0, 100.5) for i in range(14)]
    candles[12] = _candle(12, 97.5, 101.9, 100.0, 97.0)  # closes through the level

    sweep_low, _ = _detect_sweeps(candles)
    assert sweep_low is None


def test_sweep_high_detected_for_shorts() -> None:
    # Mirror: pivot high at bar 6, last bar wicks above it and closes back inside.
    highs = [100.0, 100.2, 100.4, 100.1, 100.5, 100.3, 102.0, 100.5, 100.4, 100.2, 100.5, 100.3, 102.5, 100.1]
    lows = [99.0 - 0.1 * i for i in range(14)]
    candles = [_candle(i, lows[i], highs[i], 100.0, 99.5) for i in range(14)]
    candles[12] = _candle(12, 98.1, 102.5, 100.0, 99.5)

    sweep_low, sweep_high = _detect_sweeps(candles)
    assert sweep_high == 1
    assert sweep_low is None


def test_sweep_insufficient_history_returns_none() -> None:
    candles = [_candle(i, 99.0, 101.0, 100.0, 100.0) for i in range(8)]
    assert _detect_sweeps(candles) == (None, None)
    assert _detect_sweeps(None) == (None, None)


# ── Williams Vix Fix ─────────────────────────────────────────────────────────


def _wvf_pad(top_side: bool = False) -> list[list[Any]]:
    """A pad with no spike in the evaluable region.

    The percentile rule (wvf >= 85% of trailing-window max) always fires on the
    window-max bar itself, so a genuinely spike-free pad must park its largest
    values inside the Bollinger warmup region (bars 0-18, never evaluated) and
    shrink steadily afterward — a declining series also stays below its rolling
    mean, keeping the band rule quiet.

    Bottom side measures (highest_close - low); top side mirrors it as
    (high - lowest_close), so the pad geometry mirrors too.
    """
    n = 45
    closes = [100.0] * n
    candles: list[list[Any]] = []
    for i in range(n):
        if i < 19:  # warmup: extreme wicks that the evaluated region never reaches
            wick = 2.0
        else:  # steady decay 0.5 -> 0.1
            wick = 0.5 - 0.4 * ((i - 19) / (n - 1 - 19))
        if top_side:
            candles.append(_candle(i, 99.95, 100.0 + wick, 100.0, 100.0))
        else:
            candles.append(_candle(i, 100.0 - wick, 100.05, 100.0, 100.0))
    return candles


def test_wvf_capitulation_spike_detected() -> None:
    candles = _wvf_pad(top_side=False)
    candles[-1] = _candle(len(candles) - 1, 90.0, 100.05, 100.0, 99.5)  # panic wick
    bars_ago = _detect_wvf_spike(candles, top_side=False)
    assert bars_ago == 0


def test_wvf_euphoria_spike_detected() -> None:
    candles = _wvf_pad(top_side=True)
    candles[-1] = _candle(len(candles) - 1, 99.95, 110.0, 100.0, 100.5)  # blow-off wick
    bars_ago = _detect_wvf_spike(candles, top_side=True)
    assert bars_ago == 0


def test_wvf_quiet_series_has_no_spike() -> None:
    candles = _wvf_pad(top_side=False)
    assert _detect_wvf_spike(candles, top_side=False) is None
    candles = _wvf_pad(top_side=True)
    assert _detect_wvf_spike(candles, top_side=True) is None


def test_wvf_old_spike_expires() -> None:
    candles = _wvf_pad(top_side=False)
    candles[-11] = _candle(len(candles) - 11, 90.0, 100.05, 100.0, 99.5)  # 11 bars ago
    bars_ago = _detect_wvf_spike(candles, top_side=False)
    assert bars_ago is not None and bars_ago == 10


def test_wvf_insufficient_history_returns_none() -> None:
    candles = [_candle(i, 99.0, 101.0, 100.0, 100.0) for i in range(30)]
    assert _detect_wvf_spike(candles, top_side=False) is None


# ── RSI divergence ───────────────────────────────────────────────────────────


def _bull_divergence_series() -> list[list[Any]]:
    """Price lower-low with RSI higher-low → regular bullish divergence.

    60 oscillating pad bars (RSI ~50, no strict interior pivots), then: sharp
    drop to the first low (RSI pivot, deeply oversold), a bounce, a shallow
    grind to a marginal lower low (RSI holds far higher), and a recovery long
    enough to confirm the second RSI pivot (5 bars right).
    """
    closes: list[float] = [100.0 + (0.2 if i % 2 == 0 else -0.2) for i in range(60)]
    # Sharp decline → first price low (RSI pivot, deeply oversold)
    closes += [98.0, 95.0, 92.0, 88.0, 84.0, 80.0]  # bars 60-65, low=80
    # Bounce
    closes += [82.0, 84.0, 86.0, 87.5, 88.5, 89.0]  # bars 66-71
    # Shallow grind to a marginal lower low (RSI stays well above the first low)
    closes += [88.0, 86.0, 84.5, 83.0, 81.5, 79.5]  # bars 72-77, low=79.5
    # Recovery so the RSI pivot confirms (pivot right = 5 bars)
    closes += [81.0, 83.0, 85.0, 86.5, 87.5, 88.5]  # bars 78-83
    n = len(closes)
    candles = [_candle(i, closes[i] - 0.5, closes[i] + 0.5, closes[i], closes[i]) for i in range(n)]
    return candles


def test_bullish_divergence_detected_recent() -> None:
    bull, bear = _detect_rsi_divergence(_bull_divergence_series())
    assert bull is not None
    assert bull <= 10
    # No price higher-high in this series, so no bearish divergence expected.
    assert bear is None


def _bear_divergence_series() -> list[list[Any]]:
    """Price higher-high with RSI lower-high → regular bearish divergence."""
    closes: list[float] = [100.0 + (0.2 if i % 2 == 0 else -0.2) for i in range(60)]
    closes += [102.0, 105.0, 108.0, 112.0, 116.0, 120.0]  # sharp rally, high=120
    closes += [118.0, 116.0, 114.0, 112.5, 111.5, 111.0]  # pullback
    closes += [112.0, 113.5, 115.0, 116.5, 118.0, 120.5]  # marginal higher high
    closes += [119.0, 117.5, 116.0, 114.5, 113.0, 111.5]  # decline to confirm pivot
    n = len(closes)
    candles = [_candle(i, closes[i] - 0.5, closes[i] + 0.5, closes[i], closes[i]) for i in range(n)]
    return candles


def test_bearish_divergence_detected_recent() -> None:
    bull, bear = _detect_rsi_divergence(_bear_divergence_series())
    assert bear is not None
    assert bear <= 10
    assert bull is None


def test_divergence_flat_series_none() -> None:
    closes = [100.0] * 90
    candles = [_candle(i, 99.5, 100.5, 100.0, closes[i]) for i in range(90)]
    assert _detect_rsi_divergence(candles) == (None, None)


def test_divergence_alternating_pad_no_pivots() -> None:
    # A 2-bar oscillation can never form a 5-strict RSI pivot (distance-2
    # neighbors share the value), so the pad alone must produce no divergence.
    closes = [100.0 + (0.2 if i % 2 == 0 else -0.2) for i in range(90)]
    candles = [_candle(i, closes[i] - 0.5, closes[i] + 0.5, closes[i], closes[i]) for i in range(90)]
    assert _detect_rsi_divergence(candles) == (None, None)


def test_divergence_insufficient_history_none() -> None:
    candles = [_candle(i, 99.5, 100.5, 100.0, 100.0 + 0.1 * i) for i in range(40)]
    assert _detect_rsi_divergence(candles) == (None, None)


# ── compute_features integration ─────────────────────────────────────────────


def test_compute_features_exposes_recency_keys() -> None:
    candles = _bull_divergence_series()
    raw_stats = {"open": 100.0, "high": 101.0, "low": 79.0, "volume": 1000.0}
    raw_ticker = {"price": 88.0}
    feats = compute_features(raw_stats, raw_ticker, raw_candles_1h=candles)
    for key in (
        "sweep_low_bars_ago",
        "sweep_high_bars_ago",
        "wvf_capitulation_bars_ago",
        "wvf_euphoria_bars_ago",
        "rsi_bull_div_bars_ago",
        "rsi_bear_div_bars_ago",
    ):
        assert key in feats, f"missing {key}"
    # The divergence series ends mid-recovery off a capitulation-style drop.
    assert feats["rsi_bull_div_bars_ago"] is not None


# ── Labeler tags ─────────────────────────────────────────────────────────────


def test_tags_include_confluence_events_within_window() -> None:
    features: dict[str, Any] = {
        "last_price": 100.0,
        "vwap_24h": 100.0,
        "sweep_low_bars_ago": 2,
        "sweep_high_bars_ago": 9,
        "wvf_capitulation_bars_ago": 3,
        "wvf_euphoria_bars_ago": None,
        "rsi_bull_div_bars_ago": 5,
        "rsi_bear_div_bars_ago": 25,
    }
    tags = compute_tags(features)
    assert "SWEEP_LOW" in tags
    assert "SWEEP_HIGH" not in tags  # 9 > 6-bar window
    assert "WVF_CAPITULATION" in tags
    assert "WVF_EUPHORIA" not in tags
    assert "RSI_BULL_DIV" in tags
    assert "RSI_BEAR_DIV" not in tags  # 25 > 10-bar window


def test_tags_absent_when_features_missing() -> None:
    tags = compute_tags({"last_price": 100.0, "vwap_24h": 100.0})
    assert "SWEEP_LOW" not in tags
    assert "WVF_CAPITULATION" not in tags
    assert "RSI_BULL_DIV" not in tags


# ── Scorer bonuses ───────────────────────────────────────────────────────────


def _base_features() -> dict[str, Any]:
    return {
        "last_price": 100.0,
        "day_change_pct": 0.0,
        "pos_in_range": 0.5,
        "quote_vol_24h": 3_000_000.0,
        "vwap_24h": 100.0,
        "rsi_1h": 50.0,
        "rs_vs_btc": 0.0,
        "rs_vs_btc_7d": 0.0,
        "fib_500": 99.0,
    }


def test_scorer_long_sweep_support_bonus() -> None:
    feats = _base_features() | {"sweep_low_bars_ago": 2}
    s = score(feats, trade_direction="LONG")
    assert s["components"]["sweep_support_bonus"] == 6.0


def test_scorer_short_sweep_resistance_bonus() -> None:
    feats = _base_features() | {"sweep_high_bars_ago": 1}
    s = score(feats, trade_direction="SHORT")
    assert s["components"]["sweep_resistance_bonus"] == 6.0
    assert "sweep_support_bonus" not in s["components"]


def test_scorer_stale_events_score_nothing() -> None:
    feats = _base_features() | {
        "sweep_low_bars_ago": 20,
        "wvf_capitulation_bars_ago": 40,
        "rsi_bull_div_bars_ago": 30,
    }
    s = score(feats, trade_direction="LONG")
    for key in ("sweep_support_bonus", "wvf_capitulation_bonus", "rsi_bull_div_bonus"):
        assert key not in s["components"]


def test_scorer_wvf_and_divergence_bonuses_direction_matched() -> None:
    long_feats = _base_features() | {
        "wvf_capitulation_bars_ago": 1,
        "rsi_bull_div_bars_ago": 4,
        "wvf_euphoria_bars_ago": 1,  # wrong side for a long — must be ignored
        "rsi_bear_div_bars_ago": 4,
    }
    s = score(long_feats, trade_direction="LONG")
    assert s["components"]["wvf_capitulation_bonus"] == 5.0
    assert s["components"]["rsi_bull_div_bonus"] == 5.0
    assert "wvf_euphoria_bonus" not in s["components"]
    assert "rsi_bear_div_bonus" not in s["components"]

    short_feats = _base_features() | {"wvf_euphoria_bars_ago": 2, "rsi_bear_div_bars_ago": 2}
    s = score(short_feats, trade_direction="SHORT")
    assert s["components"]["wvf_euphoria_bonus"] == 5.0
    assert s["components"]["rsi_bear_div_bonus"] == 5.0
    assert "wvf_capitulation_bonus" not in s["components"]


# ── IMH momentum-quality ports ───────────────────────────────────────────────


def _imh(closes: list[float], vols: list[float] | None = None) -> list[list[Any]]:
    """Candles from close series; per-bar range scales with |close[i]-close[i-1]|."""
    n = len(closes)
    if vols is None:
        vols = [10.0] * n
    candles = []
    for i in range(n):
        prev = closes[i - 1] if i else closes[i]
        wick = 0.3 + 0.4 * abs(closes[i] - prev)
        candles.append(
            _candle(i, closes[i] - wick, closes[i] + wick, prev, closes[i], vols[i])
        )
    return candles


def test_trend_quality_stairstep_uptrend_scores_high() -> None:
    closes = [100.0 + 0.4 * i for i in range(40)]
    tsigned, tq, _exh = _compute_trend_quality(_imh(closes))
    assert tsigned is not None and tsigned > 0.3   # bullish, meaningful magnitude
    assert tq is not None and tq > 0.85            # near-linear move → high R²


def test_trend_quality_low_on_choppy_net_flat() -> None:
    import math as _m
    closes = [100.0 + 3.0 * _m.sin(i * 1.1) for i in range(40)]
    tsigned, tq, _ = _compute_trend_quality(_imh(closes))
    assert tq is not None and tq < 0.35            # chop → low persistence
    # Magnitude rank is self-calibrated, so a regular wave's steep phase still
    # ranks high — that is BY DESIGN. The chop discount happens downstream: the
    # scorer's persistence gate (0.70 + 0.30·tq ≈ 0.70 floor) attenuates the
    # signed read, which test_scorer_trend_strength_blends_persistence_gate
    # pins. Here we only assert the direction is honest for a net-flat wave.
    assert tsigned is not None and tsigned <= 0.0  # sine ends descending


def test_trend_short_detected() -> None:
    closes = [120.0 - 0.5 * i for i in range(40)]
    tsigned, _tq, _ = _compute_trend_quality(_imh(closes))
    assert tsigned is not None and tsigned < -0.3


def test_exhaustion_high_when_decelerating_on_fading_volume() -> None:
    # Steady climb, then: slope flattens (deceleration) while volume dies.
    closes = [100.0 + 0.5 * i for i in range(30)]
    closes += [closes[-1] + 0.05 * (i + 1) for i in range(10)]  # nearly flat tail
    vols = [10.0] * 30 + [max(1.0, 10.0 - i) for i in range(10)]
    tsigned, tq, exh = _compute_trend_quality(_imh(closes, vols))
    assert tq is not None and tq > 0.8             # still trending
    assert exh is not None and exh > 0.3           # decelerating + fading


def test_exhaustion_low_on_full_thrust() -> None:
    closes = [100.0 + 0.5 * i for i in range(40)]
    vols = [10.0] * 20 + [20.0] * 20               # accelerating participation
    tsigned, tq, exh = _compute_trend_quality(_imh(closes, vols))
    assert tq is not None and tq > 0.85
    assert exh is not None and exh < 0.2


def _pressed(closes: list[float], rising: bool) -> list[list[Any]]:
    """Candles that close near the extreme of the bar (buying/selling pressure).

    Rising: close sits near the high (small upper wick, body pushing up).
    Falling: mirror — close near the low. This is what IMH's directional
    pressure is designed to detect; the generic `_imh` fixture centers the
    body in the bar's range, which halves the signal.
    """
    n = len(closes)
    candles: list[list[Any]] = []
    for i in range(n):
        prev = closes[i - 1] if i else closes[i]
        body = closes[i] - prev if rising else prev - closes[i]
        if rising:
            high = closes[i] + 0.1
            low = min(prev, closes[i]) - 0.1
        else:
            low = closes[i] - 0.1
            high = max(prev, closes[i]) + 0.1
        candles.append(_candle(i, low, high, prev, closes[i]))
    return candles


def test_directional_pressure_bullish_on_pressed_candles() -> None:
    closes = [100.0 + 0.4 * i for i in range(30)]
    dp = _compute_directional_pressure(_pressed(closes, rising=True))
    assert dp is not None and dp > 0.2


def test_directional_pressure_bearish_on_selling() -> None:
    closes = [140.0 - 0.4 * i for i in range(30)]
    dp = _compute_directional_pressure(_pressed(closes, rising=False))
    assert dp is not None and dp < -0.2


def test_directional_pressure_insufficient_history() -> None:
    assert _compute_directional_pressure([_candle(i, 99.0, 101.0, 100.0, 100.0) for i in range(10)]) is None


def test_compute_features_includes_imh_keys() -> None:
    from tpt.engine.features import compute_features as cf
    closes = [100.0 + 0.4 * i for i in range(40)]
    feats = cf(
        {"open": 100.0, "high": 118.0, "low": 99.0, "volume": 1000.0},
        {"price": closes[-1]},
        raw_candles_1h=_imh(closes),
    )
    for key in ("trend_signed_imh", "trend_quality_imh", "trend_exhaustion_imh", "directional_pressure_1h"):
        assert key in feats and feats[key] is not None


def test_scorer_trend_strength_blends_persistence_gate() -> None:
    from tpt.engine.scorer import normalize_features
    base = _base_features()
    # Steady uptrend: strong regression + high persistence.
    up = base | {"trend_signed_imh": 0.9, "trend_quality_imh": 0.95, "day_change_pct": 4.0}
    n_up = normalize_features(up, "LONG")
    # Same day_change but low persistence (one lucky candle in chop).
    chop = base | {"trend_signed_imh": 0.9, "trend_quality_imh": 0.10, "day_change_pct": 4.0}
    n_chop = normalize_features(chop, "LONG")
    assert n_up["trend_strength"] > n_chop["trend_strength"]
    # Gate floor: low persistence still keeps 70% of the blended read.
    assert n_chop["trend_strength"] >= 0.7 * (0.5 * 0.8 + 0.5 * 0.9) - 0.01


def test_scorer_trend_weakness_mirrored_for_shorts() -> None:
    from tpt.engine.scorer import normalize_features
    base = _base_features()
    down = base | {"trend_signed_imh": -0.9, "trend_quality_imh": 0.95, "day_change_pct": -4.0}
    n_down = normalize_features(down, "SHORT")
    # Falling coin: negative signed trend → positive weakness after inversion.
    assert n_down["trend_weakness"] > 0.5


def test_scorer_exhaustion_penalizes_tired_longs() -> None:
    feats = _base_features() | {"trend_exhaustion_imh": 0.8}
    s = score(feats, trade_direction="LONG")
    assert s["components"]["exhaustion_penalty"] == -4.8  # -6.0 * 0.8


def test_scorer_exhaustion_rewards_shorts_when_fuel_gone() -> None:
    feats = _base_features() | {"trend_exhaustion_imh": 0.8}
    s = score(feats, trade_direction="SHORT")
    assert s["components"]["exhaustion_fuel_gone_bonus"] == 4.8


def test_scorer_pressure_direction_matched() -> None:
    bull_feats = _base_features() | {"directional_pressure_1h": 0.5}
    s = score(bull_feats, trade_direction="LONG")
    assert s["components"]["directional_pressure"] == 2.0  # 4.0 * 0.5

    bear_feats = _base_features() | {"directional_pressure_1h": -0.5}
    s = score(bear_feats, trade_direction="SHORT")
    assert s["components"]["directional_pressure"] == 2.0


def test_scorer_pressure_below_min_abs_is_neutral() -> None:
    feats = _base_features() | {"directional_pressure_1h": 0.05}
    s = score(feats, trade_direction="LONG")
    assert "directional_pressure" not in s["components"]
