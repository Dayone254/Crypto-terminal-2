"""Multi-timeframe close pre-check — aggregation and close-state tests.

The pre-check reads the 4h/1d/1w/1M candle closes BEFORE a trade is admitted.
These tests pin the three things that make it trustworthy:

1. Aggregation correctness — 4h rolled from 1h, weeks starting on UTC Monday,
   months on the 1st, with the forming bucket's running OHLC preserved.
2. Streak honesty — a forming bar can still un-form, so it never votes on the
   settled-close streak the veto (when enabled) would act on.
3. Gate symmetry — the veto fires only on enough timeframes aligned AGAINST
   the direction, and mirrors cleanly between LONG and SHORT.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tpt.engine.timeframe_context import (
    aggregate_candles,
    analyze_close,
    build_timeframe_context,
    evaluate_timeframe_veto,
    _bucket_4h,
    _bucket_month,
    _bucket_week,
)
from tpt.config.strategy import TimeframeConfig, load_strategy

# A fixed "now": the last day of September 2026, late in the UTC day — the
# exact scenario the operator called out (monthly candle closing today).
NOW = int(datetime(2026, 9, 30, 22, 0, tzinfo=UTC).timestamp())
DAY_MIDNIGHT = int(datetime(2026, 9, 30, tzinfo=UTC).timestamp())


def _daily_series(n: int, step_pct: float = 1.0) -> list[list[float]]:
    """Chronological Coinbase-shape dailies ending at the forming daily bar.

    Every bar closes `step_pct`% above its open (a perfectly honest uptrend),
    so streaks are exactly countable.
    """
    out: list[list[float]] = []
    px = 100.0
    for i in range(n):
        ts = DAY_MIDNIGHT - (n - 1 - i) * 86400
        o = px
        c = px * (1 + step_pct / 100.0)
        # Extremes straddle whichever of open/close is on that side, so a
        # downtrend never produces the invalid high < low bar.
        out.append([ts, o, max(o, c) * 1.005, min(o, c) * 0.995, c, 10.0])
        px = c
    return out


def _hourly_series(n: int, start_ts: int) -> list[list[float]]:
    """Chronological Coinbase-shape 1h bars, each closing +0.1% above its open."""
    out: list[list[float]] = []
    px = 50.0
    for i in range(n):
        ts = start_ts + i * 3600
        o = px
        c = px * 1.001
        out.append([ts, o, c * 1.002, o * 0.998, c, 1.0])
        px = c
    return out


class TestAggregation:
    def test_4h_buckets_roll_ohlvc_correctly(self):
        # Six 1h bars spanning two 4h buckets (00:00 and 04:00 UTC).
        base = int(datetime(2026, 9, 30, 0, 0, tzinfo=UTC).timestamp())
        bars = [
            [base + 0 * 3600, 100.0, 104.0, 99.0, 102.0],
            [base + 1 * 3600, 102.0, 105.0, 101.0, 104.0],
            [base + 2 * 3600, 104.0, 106.0, 100.0, 101.0],
            [base + 3 * 3600, 101.0, 103.0, 98.0, 99.0],
            [base + 4 * 3600, 99.0, 103.0, 97.0, 102.0],
            [base + 5 * 3600, 102.0, 108.0, 101.0, 107.0],
        ]
        agg = aggregate_candles(bars, _bucket_4h)
        assert len(agg) == 2
        first, second = agg
        # Bucket 1: open of the first bar, close of the last, extremes across.
        assert first[0] == base
        assert first[1] == 100.0 and first[4] == 99.0
        assert first[2] == 106.0 and first[3] == 98.0
        # Bucket 2 (forming): running OHLC of the bars received so far.
        assert second[0] == base + 4 * 3600
        assert second[1] == 99.0 and second[4] == 107.0
        assert second[2] == 108.0 and second[3] == 97.0

    def test_binance_and_coinbase_shapes_agree(self):
        # Coinbase rows are [ts, low, high, open, close]; Binance klines are
        # [ts, open, high, low, close]. Same market, both must parse alike.
        base = DAY_MIDNIGHT
        coinbase = [[base, 99.0, 104.0, 100.0, 102.0], [base + 86400, 101.0, 106.0, 102.0, 105.0]]
        binance = [[c[0], c[3], c[2], c[1], c[4]] for c in coinbase]
        a = aggregate_candles(coinbase, _bucket_1d := (lambda ts: int(ts) // 86400 * 86400))
        b = aggregate_candles(binance, _bucket_1d)
        assert a == b
        assert a[0][1] == 100.0 and a[0][4] == 102.0  # open / close survive intact

    def test_week_buckets_start_on_utc_monday(self):
        # Wed Sep 30 and Mon Sep 28 2026 share a week; Mon Sep 21 is its own.
        wed = int(datetime(2026, 9, 30, 12, 0, tzinfo=UTC).timestamp())
        mon = int(datetime(2026, 9, 28, 3, 0, tzinfo=UTC).timestamp())
        prev_mon = int(datetime(2026, 9, 21, 9, 0, tzinfo=UTC).timestamp())
        assert _bucket_week(wed) == _bucket_week(mon)
        assert _bucket_week(mon) == int(datetime(2026, 9, 28, tzinfo=UTC).timestamp())
        assert _bucket_week(prev_mon) == int(datetime(2026, 9, 21, tzinfo=UTC).timestamp())

    def test_month_buckets_start_on_the_first(self):
        ts = int(datetime(2026, 9, 30, 22, 0, tzinfo=UTC).timestamp())
        assert _bucket_month(ts) == int(datetime(2026, 9, 1, tzinfo=UTC).timestamp())

    def test_reverse_chronological_input_is_normalised(self):
        # Coinbase returns candles newest-first; aggregation must not care.
        series = _daily_series(30)
        forward = aggregate_candles(series, _bucket_1d := (lambda ts: int(ts) // 86400 * 86400))
        backward = aggregate_candles(list(reversed(series)), _bucket_1d)
        assert forward == backward


class TestAnalyzeClose:
    def test_monthly_final_day_note_fires(self):
        # 95 dailies: the forming month is September, and "now" is its last day.
        ctx = build_timeframe_context(None, _daily_series(95), now_ts=NOW)
        assert ctx is not None
        m = ctx["tfs"]["1M"]
        assert m["forming"] is True
        assert m["days_elapsed"] == 29
        assert m["month_total_days"] == 30
        assert "final day" in (m.get("note") or "")

    def test_streak_counts_completed_bars_only(self):
        # Five green dailies; the last one is still forming at NOW, so exactly
        # four CLOSED bars vote. The forming bar must not inflate the streak.
        series = _daily_series(5)
        res = analyze_close(series, now_ts=NOW, min_bars=2)
        assert res is not None
        assert res["forming"] is True
        assert res["streak"] == 4
        assert res["close_vs_open_pct"] > 0

    def test_streak_negative_for_downtrend(self):
        series = _daily_series(6, step_pct=-1.5)
        res = analyze_close(series, now_ts=NOW)
        assert res is not None
        assert res["streak"] == -5
        assert res["close_vs_open_pct"] < 0

    def test_flat_breaks_streak(self):
        # Green, green, FLAT, green, forming: the newest completed bar is the
        # green after the flat, so the streak counts that one bar alone.
        base_px = 100.0
        bars = []
        px = base_px
        plan = [(1.0, 1.0), (1.0, 1.0), (0.0, 0.0), (1.0, 1.0), (1.0, 1.0)]
        for i, (open_off, close_off) in enumerate(plan):
            ts = DAY_MIDNIGHT - (4 - i) * 86400
            o = px
            c = px * (1 + close_off / 100.0)
            bars.append([ts, o, max(o, c) * 1.01, min(o, c) * 0.99, c, 5.0])
            px = c
        res = analyze_close(bars, now_ts=NOW)
        assert res is not None
        assert res["streak"] == 1

    def test_too_few_bars_returns_none(self):
        assert analyze_close(_daily_series(1), now_ts=NOW, min_bars=2) is None
        assert analyze_close([], now_ts=NOW) is None


class TestBuildContext:
    def test_none_without_dailies(self):
        assert build_timeframe_context(_hourly_series(48, NOW - 48 * 3600), None, now_ts=NOW) is None
        assert build_timeframe_context(None, None, now_ts=NOW) is None

    def test_all_four_timeframes_present(self):
        ctx = build_timeframe_context(
            _hourly_series(300, NOW - 299 * 3600), _daily_series(95), now_ts=NOW
        )
        assert ctx is not None
        assert set(ctx["tfs"].keys()) == {"4h", "1d", "1w", "1M"}
        assert ctx["n_timeframes"] == 4
        # The hourly series closes +0.1% per bar and dailies +1% per bar: every
        # timeframe reads up, but only settled bars vote on the aligned count.
        assert ctx["aligned_long"] >= 2
        assert ctx["aligned_short"] == 0
        # Forming daily/weekly/monthly candles are expected late on Sep 30.
        assert ctx["tfs"]["1d"]["forming"] is True
        assert ctx["tfs"]["1w"]["forming"] is True
        assert ctx["tfs"]["1M"]["forming"] is True

    def test_dailies_only_yields_three_timeframes(self):
        ctx = build_timeframe_context(None, _daily_series(95), now_ts=NOW)
        assert ctx is not None
        assert set(ctx["tfs"].keys()) == {"1d", "1w", "1M"}

    def test_short_history_limits_weekly_streaks(self):
        # 10 dailies ≈ 1.5 weeks: the weekly read exists but has little
        # completed history to vote with.
        ctx = build_timeframe_context(None, _daily_series(10), now_ts=NOW)
        assert ctx is not None
        assert ctx["tfs"]["1w"]["bars"] <= 3


class TestVeto:
    def _ctx(self, streaks: dict[str, int]) -> dict:
        return {
            "tfs": {tf: {"streak": s} for tf, s in streaks.items()},
            "aligned_long": 0,
            "aligned_short": 0,
            "n_timeframes": len(streaks),
        }

    def test_two_hostile_timeframes_veto_long(self):
        ctx = self._ctx({"1d": -3, "1w": -2, "1M": 1, "4h": 2})
        v = evaluate_timeframe_veto(ctx, "LONG")
        assert v is not None
        assert v["action"] == "SKIP"
        assert set(v["against"].keys()) == {"1d", "1w"}

    def test_short_is_mirror_image(self):
        # Same context as above, but SHORT: the two green streaks (4h +2) are
        # the only hostile read — one timeframe is context, not a veto.
        ctx = self._ctx({"1d": -3, "1w": -2, "1M": 1, "4h": 2})
        assert evaluate_timeframe_veto(ctx, "SHORT") is None

    def test_no_veto_below_threshold(self):
        ctx = self._ctx({"1d": -3, "1w": 1, "4h": -1})
        assert evaluate_timeframe_veto(ctx, "LONG") is None

    def test_stricter_timeframe_count_suppresses_veto(self):
        # With the threshold raised to three, two hostile closes are context,
        # not a veto.
        ctx = self._ctx({"1d": -3, "1w": -2, "4h": 2})
        assert evaluate_timeframe_veto(ctx, "LONG", min_timeframes=3) is None

    def test_stricter_streak_suppresses_veto(self):
        ctx = self._ctx({"1d": -3, "1w": -2})
        assert evaluate_timeframe_veto(ctx, "LONG", min_streak=4) is None

    def test_empty_context_passes(self):
        assert evaluate_timeframe_veto({}, "LONG") is None
        assert evaluate_timeframe_veto({"tfs": {}}, "LONG") is None


class TestConfigDefaults:
    def test_timeframe_block_loads_with_veto_off(self):
        cfg = load_strategy(force_reload=True)
        tf = cfg.timeframes
        assert isinstance(tf, TimeframeConfig)
        assert tf.veto_enabled is False
        assert tf.min_veto_streak == 2
        assert tf.min_veto_timeframes == 2

    def test_default_model_matches_yaml(self):
        tf = TimeframeConfig()
        assert tf.model_dump() == {
            "veto_enabled": False,
            "min_veto_streak": 2,
            "min_veto_timeframes": 2,
        }
