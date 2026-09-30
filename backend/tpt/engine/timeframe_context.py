"""Multi-timeframe close context — the pre-check read BEFORE a trade is taken.

The operator's mental model: before acting on any setup, look at what the 4h,
daily, weekly and monthly candles are actually doing — a monthly close in
particular frames the bias for everything that follows it (month → week → day).
Until now the scanner never looked at any of those closes: it fetched 1h/1d/
15m/6h candles and their tails drove every feature.

This module derives the four higher-timeframe contexts from candle data the
scan ALREADY buys:

- 4h  — aggregated from the 1h x 300 fetch (75 buckets, ~12.5 days).
- 1d  — the daily series itself (widened to ~95 bars, ~13 weeks).
- 1w  — aggregated from the dailies (~13 completed weeks).
- 1M  — aggregated from the dailies (the forming month + ~3 prior months).

No new venue calls. Coinbase exposes no 4h/weekly/monthly granularity, and
aggregating locally keeps the evidence exactly as fresh as the candles the
rest of the scan consumed.

Candle format note — two shapes arrive here:
- Binance klines:  [ts_sec, open, high, low, close, volume]
- Coinbase candles:[ts_sec, low, high, open, close, volume]
`_normalize_candles` discriminates on the only structural tell (an open can
never sit below its bar's low; low <= open almost always), so callers may pass
either shape.

Evidence-first discipline (same as the gamma families): the context attaches to
every candidate and score_breakdown for the UI and the ledger. Nothing here
vetoes a trade until `TimeframeConfig.veto_enabled` is flipped on in
config/strategy.yaml — the streak gate must prove edge in shadow before it
gates the live loop.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Timeframe keys as they appear in the context payload.
TF_4H = "4h"
TF_1D = "1d"
TF_1W = "1w"
TF_1M = "1M"

FOUR_HOURS = 4 * 3600
ONE_DAY = 86400

# Minimum buckets needed before a timeframe's close analysis means anything.
MIN_BARS_FOR_STREAK = 2


def _normalize_candles(candles: list[list[Any]]) -> list[list[float]]:
    """Return chronological [ts, open, high, low, close] rows, either input shape."""
    if not candles:
        return []
    rows = sorted(candles, key=lambda c: float(c[0]))
    # Discriminate the two formats: in Binance shape c[1] is the OPEN, which can
    # sit below c[3] (the LOW) only on exact-touch dojis; in Coinbase shape c[1]
    # is the LOW, which is <= c[3] (the OPEN) for every bar but those same dojis.
    n = checked = 0
    for c in rows[:25]:
        if len(c) >= 4:
            checked += 1
            if float(c[1]) <= float(c[3]):
                n += 1
    binance_shape = checked > 0 and (n / checked) < 0.9
    out: list[list[float]] = []
    for c in rows:
        try:
            if binance_shape:
                ts, o, h, l, cl = float(c[0]), float(c[1]), float(c[2]), float(c[3]), float(c[4])
            else:
                ts, o, h, l, cl = float(c[0]), float(c[3]), float(c[2]), float(c[1]), float(c[4])
        except (TypeError, ValueError, IndexError):
            continue
        if o > 0 and cl > 0 and h >= l:
            out.append([ts, o, h, l, cl])
    return out


def _bucket_4h(ts: float) -> int:
    return int(ts) // FOUR_HOURS * FOUR_HOURS


def _bucket_1d(ts: float) -> int:
    return int(ts) // ONE_DAY * ONE_DAY


def _bucket_week(ts: float) -> int:
    """UTC Monday 00:00:00 of the week containing ts (epoch was a Thursday)."""
    days = int(ts) // ONE_DAY
    weekday_mon0 = (days + 3) % 7  # 1970-01-01 was a Thursday (weekday 3)
    return (days - weekday_mon0) * ONE_DAY


def _bucket_month(ts: float) -> int:
    """First of the UTC month containing ts, as a unix timestamp."""
    dt = datetime.fromtimestamp(int(ts), tz=UTC)
    return int(datetime(dt.year, dt.month, 1, tzinfo=UTC).timestamp())


def aggregate_candles(
    candles: list[list[Any]],
    bucket_of: Callable[[float], int],
) -> list[list[float]]:
    """Roll lower-timeframe bars into higher-timeframe OHLC buckets.

    Input: chronological or reverse-chronological raw candles (either venue
    shape). Output: chronological [bucket_ts, open, high, low, close, volume]
    where open/close are the first/last bar in the bucket, high/low the extremes
    and volume the sum. The FORMING bucket (still receiving bars) is included —
    its running OHLC is exactly the "current close" a chart shows.
    """
    norm = _normalize_candles(candles)
    if not norm:
        return []
    buckets: dict[int, list[float]] = {}
    for ts, o, h, l, cl in norm:
        b = bucket_of(ts)
        vol_dummy = 0.0
        cur = buckets.get(b)
        if cur is None:
            buckets[b] = [float(b), o, h, l, cl, vol_dummy]
        else:
            cur[2] = max(cur[2], h)
            cur[3] = min(cur[3], l)
            cur[4] = cl  # rows are chronological: last write wins = close
    return [buckets[k] for k in sorted(buckets)]


def analyze_close(
    candles: list[list[Any]],
    now_ts: int | None = None,
    min_bars: int = MIN_BARS_FOR_STREAK,
) -> dict[str, Any] | None:
    """What is THIS timeframe's candle actually doing right now?

    The headline numbers describe the FORMING (current) bar — its running
    open/close/range is the state a human reads off the chart ("September is
    closing +4%"). `streak` is counted over COMPLETED bars only: a forming bar
    can still un-form, so it never votes on streaks. Bars need >= 5 columns
    (a ts + OHLC), which both venue shapes provide.
    """
    norm = _normalize_candles(candles)
    if len(norm) < min_bars:
        return None

    now = int(now_ts) if now_ts is not None else int(datetime.now(UTC).timestamp())

    ts, o, h, l, cl = norm[-1]
    forming = (ts + _bucket_span_hint(norm)) > now if _bucket_span_hint(norm) else False
    if o <= 0:
        return None

    rng = h - l
    close_vs_open_pct = ((cl - o) / o) * 100.0
    pos_in_range = (cl - l) / rng if rng > 0 else 0.5

    # Signed streak over completed bars only: the forming bar is excluded by
    # construction (it is the last row), so streaks describe settled closes.
    streak = 0
    completed = norm[:-1] if forming else norm
    if completed:
        def _sign(row: list[float]) -> int:
            return 1 if row[4] > row[1] else (-1 if row[4] < row[1] else 0)

        last_sign = _sign(completed[-1])
        if last_sign != 0:
            streak = last_sign
            for row in reversed(completed[:-1]):
                s = _sign(row)
                if s != last_sign:
                    break
                streak += s if (s > 0) == (streak > 0) else 0
                if s != _sign(completed[-1]):
                    break
            # recount cleanly: walk back while direction matches the newest bar
            streak = 0
            for row in reversed(completed):
                s = _sign(row)
                if s != last_sign:
                    break
                streak += s

    return {
        "bars": len(norm),
        "forming": forming,
        "open": o,
        "close": cl,
        "high": h,
        "low": l,
        "close_vs_open_pct": round(close_vs_open_pct, 3),
        "pos_in_range": round(pos_in_range, 3),
        "range_pct": round(((h - l) / l) * 100.0, 3) if l > 0 else None,
        "streak": streak,
    }


def _bucket_span_hint(norm: list[list[float]]) -> int:
    """Median gap between bucket opens — a proxy for the bucket length."""
    if len(norm) < 2:
        return 0
    gaps = [norm[i + 1][0] - norm[i][0] for i in range(len(norm) - 1)]
    gaps = [g for g in gaps if g > 0]
    if not gaps:
        return 0
    return int(sorted(gaps)[len(gaps) // 2])


def _days_elapsed_in_bucket(ts: float, now_ts: int) -> int:
    return max(0, int((now_ts - ts) // ONE_DAY))


def _month_length_days(month_start_ts: int) -> int:
    dt = datetime.fromtimestamp(month_start_ts, tz=UTC)
    if dt.month == 12:
        nxt = datetime(dt.year + 1, 1, 1, tzinfo=UTC)
    else:
        nxt = datetime(dt.year, dt.month + 1, 1, tzinfo=UTC)
    return max(1, (nxt - dt).days)


def build_timeframe_context(
    candles_1h: list[list[Any]] | None,
    candles_1d: list[list[Any]] | None,
    now_ts: int | None = None,
) -> dict[str, Any] | None:
    """Assemble the 4h/1d/1w/1M close contexts from candle data already in hand.

    Returns None when there is no daily data at all — without dailies neither
    the daily, weekly nor monthly read exists, and pretending otherwise would
    put a fabricated neutral into the evidence trail.
    """
    now = int(now_ts) if now_ts is not None else int(datetime.now(UTC).timestamp())

    daily = aggregate_candles(candles_1d or [], _bucket_1d) if candles_1d else []
    if not daily:
        return None

    tfs: dict[str, dict[str, Any]] = {}

    if candles_1h:
        agg_4h = aggregate_candles(candles_1h, _bucket_4h)
        ctx = analyze_close(agg_4h, now_ts=now)
        if ctx:
            tfs[TF_4H] = ctx

    ctx = analyze_close(daily, now_ts=now)
    if ctx:
        tfs[TF_1D] = ctx

    agg_w = aggregate_candles(daily, _bucket_week)
    ctx = analyze_close(agg_w, now_ts=now)
    if ctx:
        tfs[TF_1W] = ctx

    agg_m = aggregate_candles(daily, _bucket_month)
    ctx = analyze_close(agg_m, now_ts=now)
    if ctx:
        tfs[TF_1M] = ctx
        if ctx["forming"]:
            days_elapsed = _days_elapsed_in_bucket(int(agg_m[-1][0]), now)
            tfs[TF_1M]["days_elapsed"] = days_elapsed
            tfs[TF_1M]["month_total_days"] = _month_length_days(int(agg_m[-1][0]))
            if days_elapsed == 0:
                tfs[TF_1M]["note"] = "monthly candle just opened"
            elif days_elapsed >= tfs[TF_1M]["month_total_days"] - 1:
                tfs[TF_1M]["note"] = "final day of the monthly candle — its close sets next month's bias"

    if not tfs:
        return None

    aligned_long = sum(1 for c in tfs.values() if c.get("streak", 0) >= 2)
    aligned_short = sum(1 for c in tfs.values() if c.get("streak", 0) <= -2)

    return {
        "tfs": tfs,
        "aligned_long": aligned_long,
        "aligned_short": aligned_short,
        "n_timeframes": len(tfs),
    }


def evaluate_timeframe_veto(
    ctx: dict[str, Any],
    trade_direction: str,
    min_streak: int = 2,
    min_timeframes: int = 2,
) -> dict[str, Any] | None:
    """Should the higher-timeframe closes stand down this direction?

    A veto needs at least `min_timeframes` of the available closes in a settled
    streak (>= `min_streak` completed bars) AGAINST the trade direction. One
    hostile timeframe is context, not a veto; two-plus is a structure the setup
    would be fighting. Returns a dict describing the refusal, or None to pass.
    """
    if not ctx or not ctx.get("tfs"):
        return None

    against: dict[str, int] = {}
    for tf, c in ctx["tfs"].items():
        s = int(c.get("streak") or 0)
        if trade_direction == "LONG" and s <= -min_streak:
            against[tf] = s
        elif trade_direction == "SHORT" and s >= min_streak:
            against[tf] = s

    if len(against) < min_timeframes:
        return None

    detail = ", ".join(f"{tf} streak {s:+d}" for tf, s in sorted(against.items()))
    return {
        "action": "SKIP",
        "reason": (
            f"{len(against)} higher-timeframe closes aligned against "
            f"{trade_direction} ({detail})"
        ),
        "min_streak": min_streak,
        "against": against,
    }
