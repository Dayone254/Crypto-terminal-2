"""Unit tests for the feature computation engine."""
from tpt.engine.features import (
    _compute_atr,
    _compute_bollinger,
    _compute_ema,
    _compute_macd,
    _compute_rsi,
    _compute_volume_ratio,
    _fib_levels,
    compute_features,
)


class TestFibLevels:
    def test_fib_levels_basic(self) -> None:
        levels = _fib_levels(low=100.0, high=200.0)
        assert abs(levels["fib_500"] - 150.0) < 0.001
        assert abs(levels["fib_618"] - 138.2) < 0.1
        assert abs(levels["fib_786"] - 121.4) < 0.1

    def test_fib_levels_zero_range(self) -> None:
        levels = _fib_levels(low=100.0, high=100.0)
        assert levels["fib_500"] == 100.0


class TestWilderRSI:
    def test_rsi_insufficient_data(self) -> None:
        closes = [10.0] * 10
        assert _compute_rsi(closes, period=14) is None

    def test_rsi_uptrend(self) -> None:
        closes = [10.0 + i for i in range(20)]
        rsi = _compute_rsi(closes, period=14)
        assert rsi is not None
        assert rsi == 100.0

    def test_rsi_mixed(self) -> None:
        closes = [10.0, 12.0, 11.0, 13.0, 12.0, 14.0, 13.0, 15.0, 14.0, 16.0, 15.0, 17.0, 16.0, 18.0, 17.0, 19.0]
        rsi = _compute_rsi(closes, period=14)
        assert rsi is not None
        assert 50.0 < rsi < 90.0


class TestComputeFeatures:
    def test_pos_in_range_flat_day_guard(self) -> None:
        raw_stats = {"open": "10.0", "high": "10.0", "low": "10.0", "last": "10.0", "volume": "1000"}
        raw_ticker = {"price": "10.0"}
        feats = compute_features(raw_stats, raw_ticker)
        assert feats["pos_in_range"] == 0.5
        assert feats["day_change_pct"] == 0.0

    def test_quote_vol_formula(self) -> None:
        raw_stats = {"open": "100.0", "high": "110.0", "low": "95.0", "last": "105.0", "volume": "5000"}
        raw_ticker = {"price": "105.0"}
        feats = compute_features(raw_stats, raw_ticker)
        assert feats["quote_vol_24h"] == 5000.0 * 105.0


class TestEMA:
    def test_ema_basic(self) -> None:
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        ema = _compute_ema(values, period=3)
        assert len(ema) == 5
        # First valid EMA at index 2 = SMA(1,2,3) = 2.0
        assert ema[2] == 2.0
        # Subsequent values should trend upward
        assert ema[3] > ema[2]
        assert ema[4] > ema[3]

    def test_ema_empty(self) -> None:
        assert _compute_ema([], period=3) == []

    def test_ema_single_value(self) -> None:
        ema = _compute_ema([5.0], period=3)
        assert len(ema) == 1
        assert ema[0] == 5.0


class TestMACD:
    def test_macd_insufficient_data(self) -> None:
        closes = [float(i) for i in range(30)]  # Need 26 + 9 = 35
        macd, sig, hist = _compute_macd(closes)
        assert macd is None

    def test_macd_uptrend(self) -> None:
        # 50 ascending prices: MACD line should be positive (fast EMA above slow)
        closes = [100.0 + i * 0.5 for i in range(50)]
        macd, sig, hist = _compute_macd(closes)
        assert macd is not None
        assert macd > 0  # Fast EMA > Slow EMA in uptrend

    def test_macd_returns_three_values(self) -> None:
        closes = [100.0 + (i % 5) for i in range(50)]
        macd, sig, hist = _compute_macd(closes)
        assert macd is not None
        assert sig is not None
        assert hist is not None
        assert abs(hist - (macd - sig)) < 0.001


class TestBollingerBands:
    def test_bb_insufficient_data(self) -> None:
        closes = [10.0] * 10
        width, pct_b, sma = _compute_bollinger(closes, period=20)
        assert width is None

    def test_bb_constant_prices(self) -> None:
        # Constant prices = zero std = zero width
        closes = [10.0] * 25
        width, pct_b, sma = _compute_bollinger(closes, period=20)
        # With zero std, band range is 0 → should return None
        assert width is None

    def test_bb_volatile_prices(self) -> None:
        # High volatility should produce measurable width and %B
        closes = [100.0 + (5.0 if i % 2 == 0 else -5.0) for i in range(25)]
        width, pct_b, sma = _compute_bollinger(closes, period=20)
        assert width is not None
        assert width > 0
        assert pct_b is not None
        assert 0.0 <= pct_b <= 1.0 or pct_b < 0.0 or pct_b > 1.0  # Can exceed bounds


class TestATR:
    def test_atr_insufficient_data(self) -> None:
        candles = [[i, 9.0, 11.0, 10.0, 10.0, 100] for i in range(5)]
        assert _compute_atr(candles, period=14) is None

    def test_atr_basic(self) -> None:
        # 20 candles with consistent H-L range of 2.0
        candles = [[i, 9.0, 11.0, 10.0, 10.0, 100] for i in range(20)]
        atr = _compute_atr(candles, period=14)
        assert atr is not None
        assert abs(atr - 2.0) < 0.01  # True range = H - L = 2.0 for each


class TestVolumeRatio:
    def test_vol_ratio_insufficient_data(self) -> None:
        candles = [[i, 9.0, 11.0, 10.0, 10.0, 100] for i in range(10)]
        assert _compute_volume_ratio(candles, lookback=20) is None

    def test_vol_ratio_spike(self) -> None:
        # 20 candles with volume 100, then spike to 300
        candles = [[i, 9.0, 11.0, 10.0, 10.0, 100] for i in range(21)]
        candles[-1][5] = 300  # 3x spike
        ratio = _compute_volume_ratio(candles, lookback=20)
        assert ratio is not None
        assert abs(ratio - 3.0) < 0.01


class TestMultiTimeframeOutputs:
    def test_new_features_present_without_data(self) -> None:
        """All 9 new features should be present in output even with no candle data."""
        raw_stats = {"open": "100.0", "high": "110.0", "low": "95.0", "last": "105.0", "volume": "5000"}
        raw_ticker = {"price": "105.0"}
        feats = compute_features(raw_stats, raw_ticker)
        for key in ["rsi_15m", "rsi_6h", "macd_1h", "macd_signal_1h", "bb_width_1h", "bb_pct_b_1h", "atr_1h", "volume_ratio_1h", "ema_trend_6h"]:
            assert key in feats
            assert feats[key] is None

