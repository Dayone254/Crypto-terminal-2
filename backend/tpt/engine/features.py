"""Feature computation engine — pure functions only. No I/O.

All functions are deterministic given raw stats, ticker, and candle inputs.
"""
from __future__ import annotations

import time
from typing import Any

FeatureDict = dict[str, Any]


def _fib_levels(low: float, high: float) -> dict[str, float]:
    """Return fib retrace price levels for given impulse (low → high)."""
    diff = high - low
    if diff <= 0:
        return {
            "fib_236": high,
            "fib_382": high,
            "fib_500": high,
            "fib_618": high,
            "fib_786": high,
        }
    return {
        "fib_236": high - 0.236 * diff,
        "fib_382": high - 0.382 * diff,
        "fib_500": high - 0.500 * diff,
        "fib_618": high - 0.618 * diff,
        "fib_786": high - 0.786 * diff,
    }


def _return_pct(candles: list[list[Any]] | None, lookback: int) -> float | None:
    """Percent return over the last ``lookback`` candles. Candles must be oldest first.

    Returns None when history is too short to measure the horizon honestly — a
    fabricated return is worse than a missing one, because the scorer cannot tell
    a guess from an observation.
    """
    if not candles:
        return None
    closes = [float(c[4]) for c in candles if len(c) >= 5]
    if len(closes) < lookback + 1:
        return None
    past = closes[-(lookback + 1)]
    if past <= 0:
        return None
    return round((closes[-1] / past - 1.0) * 100.0, 4)


def multi_horizon_returns(
    raw_candles_1h: list[list[Any]] | None,
    raw_candles_1d: list[list[Any]] | None,
) -> dict[str, float | None]:
    """Returns over 1h / 24h / 7d / 30d / 60d.

    Used to build the relative-strength benchmark (BTC) and each symbol's own
    returns, so both sides of the comparison are measured by the same code over
    the same windows.
    """
    sorted_1h = sorted(raw_candles_1h, key=lambda c: float(c[0])) if raw_candles_1h else None
    sorted_1d = sorted(raw_candles_1d, key=lambda c: float(c[0])) if raw_candles_1d else None
    return {
        "ret_1h": _return_pct(sorted_1h, 1),
        "ret_24h": _return_pct(sorted_1h, 24),
        "ret_7d": _return_pct(sorted_1d, 7),
        "ret_30d": _return_pct(sorted_1d, 30),
        "ret_60d": _return_pct(sorted_1d, 60),
    }


def _compute_rsi(closes: list[float], period: int = 14) -> float | None:
    """Compute RSI using Wilder's smoothing.

    `closes` must be ordered oldest first (chronological).
    Returns None if there are fewer than period + 1 prices.
    """
    if len(closes) < period + 1:
        return None

    gains: list[float] = []
    losses: list[float] = []

    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        if diff > 0:
            gains.append(diff)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(-diff)

    if len(gains) < period:
        return None

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return round(rsi, 2)


def _compute_vwap(candles: list[list[Any]]) -> float | None:
    """Compute VWAP from OHLCV candle array (up to 24 candles).
    
    Coinbase candle structure: [time, low, high, open, close, volume]
    Returns None if candles is empty or volume total is zero.
    """
    if not candles:
        return None

    pv_sum = 0.0
    vol_sum = 0.0

    # Ensure 24h window limit — sort newest-first so we always take the
    # most recent 24 candles, not the oldest 24 from a newest-first Coinbase response.
    target_candles = sorted(candles, key=lambda c: float(c[0]), reverse=True)[:24]

    for c in target_candles:
        if len(c) < 6:
            continue
        low = float(c[1])
        high = float(c[2])
        close = float(c[4])
        vol = float(c[5])

        typical_price = (high + low + close) / 3.0
        pv_sum += typical_price * vol
        vol_sum += vol

    if vol_sum <= 0:
        return None

    return pv_sum / vol_sum


def _compute_ema(values: list[float], period: int) -> list[float]:
    """Compute Exponential Moving Average series.

    Returns list of same length as input, with None-equivalent early values
    replaced by SMA seed. `values` must be ordered oldest first.
    """
    if not values or period <= 0:
        return []
    k = 2.0 / (period + 1)
    ema_vals: list[float] = []
    # Seed with SMA of first `period` values
    if len(values) < period:
        sma = sum(values) / len(values)
        ema_vals.append(sma)
        for v in values[1:]:
            ema_vals.append(ema_vals[-1] * (1 - k) + v * k)
        return ema_vals
    sma = sum(values[:period]) / period
    ema_vals = [0.0] * (period - 1) + [sma]
    for v in values[period:]:
        ema_vals.append(ema_vals[-1] * (1 - k) + v * k)
    return ema_vals


def _compute_macd(
    closes: list[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[float | None, float | None, float | None]:
    """Compute MACD line, signal line, and histogram.

    Returns (macd, signal, histogram) or (None, None, None) if insufficient data.
    """
    if len(closes) < slow + signal:
        return None, None, None
    ema_fast = _compute_ema(closes, fast)
    ema_slow = _compute_ema(closes, slow)
    # MACD line = EMA(fast) - EMA(slow), only valid from index slow-1 onward
    macd_line = [ema_fast[i] - ema_slow[i] for i in range(slow - 1, len(closes))]
    if len(macd_line) < signal:
        return None, None, None
    signal_line = _compute_ema(macd_line, signal)
    macd_val = macd_line[-1]
    signal_val = signal_line[-1]
    histogram = macd_val - signal_val
    return round(macd_val, 6), round(signal_val, 6), round(histogram, 6)


def _compute_bollinger(
    closes: list[float], period: int = 20, num_std: float = 2.0
) -> tuple[float | None, float | None, float | None]:
    """Compute Bollinger Band width and %B.

    Returns (bb_width, bb_pct_b, sma) or (None, None, None) if insufficient data.
    bb_width = (upper - lower) / sma  (normalized volatility measure)
    bb_pct_b = (price - lower) / (upper - lower)  (position within bands)
    """
    if len(closes) < period:
        return None, None, None
    window = closes[-period:]
    sma = sum(window) / period
    if sma <= 0:
        return None, None, None
    variance = sum((x - sma) ** 2 for x in window) / period
    std = variance ** 0.5
    upper = sma + num_std * std
    lower = sma - num_std * std
    band_range = upper - lower
    if band_range <= 0:
        return None, None, None
    bb_width = round(band_range / sma, 6)
    bb_pct_b = round((closes[-1] - lower) / band_range, 4)
    return bb_width, bb_pct_b, round(sma, 6)


def _compute_atr(candles: list[list[Any]], period: int = 14) -> float | None:
    """Compute ATR from OHLCV candles. Candles must be sorted oldest first."""
    if len(candles) < period + 1:
        return None
    true_ranges: list[float] = []
    for i in range(1, len(candles)):
        prev_close = float(candles[i - 1][4])
        h = float(candles[i][2])
        lo = float(candles[i][1])
        tr = max(h - lo, abs(h - prev_close), abs(lo - prev_close))
        true_ranges.append(tr)
    if len(true_ranges) < period:
        return None
    return sum(true_ranges[-period:]) / min(len(true_ranges), period)


def _compute_volume_ratio(candles: list[list[Any]], lookback: int = 20) -> float | None:
    """Compute current candle volume / SMA(lookback) of volume with Time-Weighted projection.

    Candles must be sorted oldest first. Returns None if insufficient data.
    """
    if len(candles) < lookback + 1:
        return None
        
    # Validate minimum structure to pull interval size
    if len(candles) < 2:
        return None

    vols = [float(c[5]) for c in candles if len(c) >= 6]
    if len(vols) < lookback + 1:
        return None
        
    avg_vol = sum(vols[-(lookback + 1):-1]) / lookback
    if avg_vol <= 0:
        return None
        
    active_vol = vols[-1]
    
    # Time-Weighted Projection
    try:
        active_ts = float(candles[-1][0])
        prev_ts = float(candles[-2][0])
        interval_sec = active_ts - prev_ts
        
        now_ts = time.time()
        elapsed_sec = now_ts - active_ts
        
        # Fallback to absolute if time math is unsafe (e.g., disconnected local clock or historical backtest sweep)
        if interval_sec <= 0 or elapsed_sec <= 0 or elapsed_sec > interval_sec:
            return round(active_vol / avg_vol, 4)
            
        elapsed_pct = elapsed_sec / interval_sec
        
        # Floor Guard: Do not project early noise (wait until at least 20% formed)
        if elapsed_pct < 0.20:
            return round(active_vol / avg_vol, 4)
            
        projected_vol = active_vol / elapsed_pct
        return round(projected_vol / avg_vol, 4)
    except Exception:
        # Absolute base fallback
        return round(active_vol / avg_vol, 4)


# ── Confluence detectors (ported from the operator's Pine entry system) ──────
#
# Three bar-pattern detectors that share a common shape: a discrete event fires
# on some bar, and the feature records HOW RECENTLY it fired (bars ago) rather
# than a boolean. The scorer/labeler then apply their own freshness window.
# This mirrors the Pine system's `ta.barssince(event) <= window` pattern and
# keeps the raw recency available for later empirical tuning of the windows.
#
# All are pure candle math over the 1h series the scanner already fetches —
# no new API calls, no new pipeline stages.

# A sweep only satisfies a freshness gate if it happened within this many bars.
SWEEP_FRESHNESS_BARS = 6
# Capitulation / euphoria spikes stay "recent" for this many bars.
WVF_SPIKE_WINDOW_BARS = 10
# A confirmed RSI divergence stays "recent" for this many bars.
DIV_RECENT_WINDOW_BARS = 10

# Sweep pivot half-width (bars each side of a candidate swing point).
SWEEP_PIVOT_LEN = 5

# Williams Vix Fix parameters (Chris Moody's CM_Williams_Vix_Fix, own port).
WVF_PERIOD = 22        # lookback for the highest-close anchor
WVF_BB_LEN = 20        # Bollinger window over the WVF series
WVF_BB_MULT = 2.0      # Bollinger width in standard deviations
WVF_PCT_LOOKBACK = 50  # percentile window over the WVF series
WVF_PCT_THRESH = 0.85  # spike fires at/above this fraction of the window max

# RSI divergence parameters (regular divergence only).
DIV_RSI_LEN = 14
DIV_PIVOT_LEFT = 5
DIV_PIVOT_RIGHT = 5
DIV_MIN_GAP = 5       # min bars between the two pivots
DIV_MAX_GAP = 60      # max bars between the two pivots


def _detect_sweeps(candles: list[list[Any]] | None) -> tuple[int | None, int | None]:
    """Detect liquidity sweeps on the 1h candles.

    A sweep is a wick that pierces the most recent unbroken swing point while
    price closes back inside it — resting liquidity beyond the level got taken
    and rejected. A genuine close-through invalidates the level instead (that
    is a break, not a sweep).

    Returns ``(sweep_low_bars_ago, sweep_high_bars_ago)`` where each value is
    the recency in bars of the most recent sweep of that side, or ``None`` if
    no sweep occurred (or the level was closed through first). Swept lows gate
    long reversals; swept highs gate short reversals.
    """
    if not candles or len(candles) < SWEEP_PIVOT_LEN * 2 + 3:
        return None, None
    highs = [float(c[2]) for c in candles if len(c) >= 6]
    lows = [float(c[1]) for c in candles if len(c) >= 6]
    closes = [float(c[4]) for c in candles if len(c) >= 6]
    n = min(len(highs), len(lows), len(closes))
    if n < SWEEP_PIVOT_LEN * 2 + 3:
        return None, None
    L = SWEEP_PIVOT_LEN

    def _most_recent_pivot(is_high: bool) -> int | None:
        """Newest confirmed swing point with at least L bars after it."""
        for i in range(n - 1 - L, L - 1, -1):
            if is_high:
                if (
                    highs[i] > max(highs[i - L:i])
                    and highs[i] > max(highs[i + 1:i + 1 + L])
                ):
                    return i
            else:
                if (
                    lows[i] < min(lows[i - L:i])
                    and lows[i] < min(lows[i + 1:i + 1 + L])
                ):
                    return i
        return None

    def _sweep_bars_ago(pivot_idx: int, level: float, is_high: bool) -> int | None:
        """Recency of the most recent sweep of ``level``, or None.

        Walking forward from the pivot: a close through kills the level (any
        sweep that happened before the break still counts, matching the Pine
        implementation's barssince semantics), a wick-through-with-close-back
        is the sweep event.
        """
        last_sweep: int | None = None
        for j in range(pivot_idx + 1, n):
            wick_through = highs[j] > level if is_high else lows[j] < level
            close_through = closes[j] > level if is_high else closes[j] < level
            if close_through:
                return last_sweep
            if wick_through:
                last_sweep = n - 1 - j
        return last_sweep

    ph = _most_recent_pivot(is_high=True)
    sweep_high = _sweep_bars_ago(ph, highs[ph], True) if ph is not None else None
    pl = _most_recent_pivot(is_high=False)
    sweep_low = _sweep_bars_ago(pl, lows[pl], False) if pl is not None else None
    return sweep_low, sweep_high


def _detect_wvf_spike(candles: list[list[Any]] | None, top_side: bool) -> int | None:
    """Williams Vix Fix spike recency, in bars ago (None if none / not enough data).

    Bottom side (``top_side=False``) measures panic: distance of the bar's low
    from the highest close of the trailing window. Top side mirrors it for
    euphoria: distance of the bar's high from the LOWEST close — a genuine
    short-side counterpart rather than a negation of the long condition.
    A spike fires when the WVF value exceeds its Bollinger band OR reaches the
    85th percentile of its trailing window.
    """
    if not candles or len(candles) < WVF_PERIOD + WVF_BB_LEN:
        return None
    highs = [float(c[2]) for c in candles if len(c) >= 6]
    lows = [float(c[1]) for c in candles if len(c) >= 6]
    closes = [float(c[4]) for c in candles if len(c) >= 6]
    n = min(len(highs), len(lows), len(closes))
    if n < WVF_PERIOD + WVF_BB_LEN:
        return None

    wvf: list[float] = []
    for i in range(n):
        lo = max(0, i - WVF_PERIOD + 1)
        if top_side:
            base = min(closes[lo:i + 1])
            wvf.append((highs[i] - base) / base * 100.0 if base > 0 else 0.0)
        else:
            peak = max(closes[lo:i + 1])
            wvf.append((peak - lows[i]) / peak * 100.0 if peak > 0 else 0.0)

    last_spike: int | None = None
    for i in range(WVF_BB_LEN - 1, n):
        window = wvf[i - WVF_BB_LEN + 1:i + 1]
        mean = sum(window) / len(window)
        var = sum((x - mean) ** 2 for x in window) / len(window)
        std = var ** 0.5
        pct_window = wvf[max(0, i - WVF_PCT_LOOKBACK + 1):i + 1]
        pct_thresh = max(pct_window) * WVF_PCT_THRESH
        # The band test requires the value to actually exceed the band mean: on a
        # perfectly flat series (std == 0) `wvf >= mean + 2*0` would otherwise
        # flag every bar as a spike. Real dead-market data does produce std == 0.
        band_spike = wvf[i] > mean and wvf[i] >= mean + WVF_BB_MULT * std
        if band_spike or wvf[i] >= pct_thresh:
            last_spike = n - 1 - i
    return last_spike


def _compute_rsi_series(closes: list[float], period: int = 14) -> list[float | None]:
    """Full Wilder RSI series (None for the first ``period`` slots)."""
    out: list[float | None] = [None] * len(closes)
    if len(closes) < period + 1:
        return out
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    out[period] = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out[i + 1] = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    return out


def _detect_rsi_divergence(candles: list[list[Any]] | None) -> tuple[int | None, int | None]:
    """Regular RSI divergence recency on the 1h closes.

    Bullish: price makes a lower low while RSI makes a higher low (sellers
    exhausting). Bearish: price higher high while RSI lower high (buyers
    exhausting). Divergences only confirm ``DIV_PIVOT_RIGHT`` bars after the
    RSI pivot — the returned recency is measured from that confirmation bar,
    matching the Pine implementation (no repaint, no lookahead).

    Returns ``(bull_bars_ago, bear_bars_ago)``, each None when absent.
    """
    if not candles or len(candles) < DIV_MAX_GAP + 2 * (DIV_PIVOT_LEFT + DIV_PIVOT_RIGHT):
        return None, None
    closes = [float(c[4]) for c in candles if len(c) >= 5]
    if len(closes) < DIV_MAX_GAP + 2 * (DIV_PIVOT_LEFT + DIV_PIVOT_RIGHT):
        return None, None
    rsi = _compute_rsi_series(closes, DIV_RSI_LEN)
    n = len(closes)
    L, R = DIV_PIVOT_LEFT, DIV_PIVOT_RIGHT

    def _pivots(is_high: bool) -> list[tuple[int, float]]:
        piv: list[tuple[int, float]] = []
        for i in range(L, n - R):
            v = rsi[i]
            if v is None:
                continue
            window = [rsi[j] for j in range(i - L, i + R + 1) if j != i and rsi[j] is not None]
            if len(window) < L + R:
                continue
            if is_high and all(v > w for w in window):
                piv.append((i, v))
            if not is_high and all(v < w for w in window):
                piv.append((i, v))
        return piv

    def _divergence_bars_ago(pivots: list[tuple[int, float]], price_lower: bool) -> int | None:
        """Most recent qualifying divergence, measured from its confirmation bar."""
        for k in range(len(pivots) - 1, 0, -1):
            i0, v0 = pivots[k - 1]
            i1, v1 = pivots[k]
            gap = i1 - i0
            if not (DIV_MIN_GAP <= gap <= DIV_MAX_GAP):
                continue
            price_ok = closes[i1] < closes[i0] if price_lower else closes[i1] > closes[i0]
            rsi_ok = v1 > v0 if price_lower else v1 < v0
            if price_ok and rsi_ok:
                return (n - 1) - (i1 + R)
        return None

    bull = _divergence_bars_ago(_pivots(is_high=False), price_lower=True)
    bear = _divergence_bars_ago(_pivots(is_high=True), price_lower=False)
    return bull, bear


# ── IMH momentum-quality engine (ported from the operator's IMH V7) ─────────
#
# Three continuous features measuring HOW a move happens, not just how much:
#   - trend quality: ATR-normalized regression slope, percentile-ranked against
#     its own history, gated by R² persistence (a grinding stair-step scores
#     high; one big day inside chop scores low).
#   - trend exhaustion: high persistence × deceleration against the trend ×
#     fading participation — the pre-rollover signature.
#   - directional pressure: close-location + body + wick imbalance, scaled by
#     relative volume — is this move being pressed by real participation.
#
# All percentile ranks use the same self-calibration philosophy as IMH: values
# are normalized against their own trailing window, so thresholds adapt to
# each symbol's volatility character instead of fixed scalars.

IMH_LR_LEN = 21           # regression / ATR / effort window
IMH_CALIBRATION = 100     # percentile-rank window for slope & acceleration
IMH_VOL_BASELINE = 20     # relative-volume SMA window
IMH_VOL_Z_BASELINE = 100  # volume z-score baseline


def _linreg_slope(values: list[float], length: int) -> float | None:
    """Slope of the linear regression of the last ``length`` values (per bar).

    Equivalent to Pine's ta.linreg(v, len, 0) - ta.linreg(v, len, 1).
    Returns None while there is less than ``length`` samples.
    """
    if len(values) < length:
        return None
    window = values[-length:]
    n = float(length)
    xs = list(range(length))
    mean_x = (n - 1) / 2.0
    mean_y = sum(window) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom <= 0:
        return None
    beta = sum((xs[i] - mean_x) * (window[i] - mean_y) for i in range(length)) / denom
    return beta


def _percentile_rank(values: list[float], current: float, inclusive: bool = True) -> float | None:
    """Percentile rank of ``current`` within ``values`` [0, 100]. None if empty.

    ``inclusive=True`` matches Pine's ta.percentrank (values <= current count),
    so a steady series pins at 100 — the desired reading for slope magnitude in
    an established trend. ``inclusive=False`` counts strictly-less values, so
    ties rank 0 — the desired reading for deceleration, where an all-zero
    history must NOT read as maximal deceleration.
    """
    if not values:
        return None
    if inclusive:
        count = sum(1 for v in values if v <= current)
    else:
        count = sum(1 for v in values if v < current)
    return count / len(values) * 100.0


def _compute_trend_quality(candles: list[list[Any]] | None) -> tuple[float | None, float | None, float | None]:
    """(trend_signed, trend_quality, exhaustion_score) from 1h closes.

    trend_signed ∈ [-1, 1]: sign of the raw regression slope × percentile rank
    of |slope| (direction from the slope itself, magnitude self-calibrated —
    IMH V7's 'Slope Sign' mode; the legacy rank-sign mode misread steady
    downtrends as bullish because percentrank ties pin near 100).

    trend_quality ∈ [0, 1]: R² of close-vs-time (persistence) — how linear the
    recent move is, regardless of direction.

    exhaustion_score ∈ [0, 1]: persistence × deceleration-against-trend ×
    participation-fade. High values mark vertical moves losing institutional
    fuel — the pre-rollover signature for shorts (and a chase warning for
    longs).
    """
    if not candles or len(candles) < IMH_LR_LEN + 2:
        return None, None, None
    closes = [float(c[4]) for c in candles if len(c) >= 5]
    vols = [float(c[5]) for c in candles if len(c) >= 6]
    if len(closes) < IMH_LR_LEN + 2:
        return None, None, None

    # Slope series (one per bar, once enough history exists) for rank context.
    slopes: list[float] = []
    for i in range(IMH_LR_LEN, len(closes) + 1):
        s = _linreg_slope(closes[:i], IMH_LR_LEN)
        if s is not None:
            slopes.append(s)
    if len(slopes) < 5:
        return None, None, None

    current_slope = slopes[-1]
    atr = _compute_atr(candles, IMH_LR_LEN) or 0.0
    scale = max(atr, 1e-7)
    slope_ratio = current_slope / scale

    # Magnitude: percentile rank of |slope| against its own history (inclusive,
    # Pine semantics — a steady trend pins at full strength).
    abs_ratios = [abs(s) / scale for s in slopes]
    mag_rank = _percentile_rank(abs_ratios[:-1], abs(abs_ratios[-1]), inclusive=True)
    if mag_rank is None:
        return None, None, None
    trend_signed = (1.0 if current_slope > 0 else -1.0 if current_slope < 0 else 0.0) * (mag_rank / 100.0)

    # Persistence: R² of close vs time over the regression window.
    window = closes[-IMH_LR_LEN:]
    n = float(IMH_LR_LEN)
    xs = list(range(IMH_LR_LEN))
    mean_x = (n - 1) / 2.0
    mean_y = sum(window) / n
    denom_x = sum((x - mean_x) ** 2 for x in xs)
    if denom_x <= 0:
        return None, None, None
    beta = sum((xs[i] - mean_x) * (window[i] - mean_y) for i in range(IMH_LR_LEN)) / denom_x
    alpha = mean_y - beta * mean_x
    ss_tot = sum((y - mean_y) ** 2 for y in window)
    ss_res = sum((window[i] - (alpha + beta * xs[i])) ** 2 for i in range(IMH_LR_LEN))
    persistence = 0.0 if ss_tot <= 0 else max(0.0, 1.0 - ss_res / ss_tot)
    trend_quality = persistence

    # Exhaustion: deceleration against the trend × participation fade.
    # Deceleration is SELF-CALIBRATED like IMH: the raw slope decline (per bar,
    # ATR-normalized) is percentile-ranked against its own trailing history
    # (strict — an all-zero history must rank 0, not 100). The 21-bar regression
    # window smooths a stall, so a raw decel threshold would fire far too late;
    # "unusual for this symbol" is the honest test.
    decels: list[float] = []
    for i in range(1, len(slopes)):
        prev_s, cur_s = slopes[i - 1], slopes[i]
        if prev_s * cur_s > 0:  # same-direction legs only
            decels.append(max(0.0, (abs(prev_s) - abs(cur_s)) / scale))
        else:
            decels.append(0.0)
    current_decel = decels[-1] if decels else 0.0
    decel_context = decels[-IMH_CALIBRATION:-1]
    decel_rank = _percentile_rank(decel_context, current_decel, inclusive=False)
    deceleration = (decel_rank / 100.0) if decel_rank is not None else 0.0
    rel_vol: float | None = None
    if len(vols) >= IMH_VOL_BASELINE + 1:
        avg_vol = sum(vols[-(IMH_VOL_BASELINE + 1):-1]) / IMH_VOL_BASELINE
        if avg_vol > 0:
            rel_vol = vols[-1] / avg_vol
    participation_fade = 1.0 if rel_vol is None else max(0.0, min(1.0, 1.0 - (rel_vol - 0.5) / 1.5))
    exhaustion = persistence * deceleration * participation_fade

    return round(trend_signed, 4), round(trend_quality, 4), round(exhaustion, 4)


def _compute_directional_pressure(candles: list[list[Any]] | None) -> float | None:
    """Directional pressure × relative volume, EMA-smoothed (IMH volume engine).

    Per bar: 0.40·close_location + 0.40·body_pressure + 0.20·wick_imbalance,
    each in [-1, 1], scaled by relative volume (vol / SMA-20), then smoothed
    with a 3-bar EMA. Positive = buyers pressing with participation; negative
    = sellers pressing. None when candle history is too short.
    """
    if not candles or len(candles) < IMH_VOL_BASELINE + 4:
        return None
    # chronological: [time, low, high, open, close, volume]
    rows = [c for c in candles if len(c) >= 6]
    if len(rows) < IMH_VOL_BASELINE + 4:
        return None

    pressures: list[float] = []
    rel_vols: list[float] = []
    for i in range(1, len(rows)):
        low = float(rows[i][1])
        high = float(rows[i][2])
        open_ = float(rows[i][3])
        close = float(rows[i][4])
        vol = float(rows[i][5])
        rng = max(high - low, 1e-9)
        close_location = ((close - low) - (high - close)) / rng
        body_pressure = (close - open_) / rng
        upper_wick = high - max(close, open_)
        lower_wick = min(close, open_) - low
        wick_imbalance = (lower_wick - upper_wick) / rng
        pressures.append(0.40 * close_location + 0.40 * body_pressure + 0.20 * wick_imbalance)
        window_vols = [float(r[5]) for r in rows[max(0, i - IMH_VOL_BASELINE):i]]
        avg_vol = sum(window_vols) / len(window_vols) if window_vols else 0.0
        rel_vols.append(vol / avg_vol if avg_vol > 0 else 1.0)

    # Combine and smooth with a 3-bar EMA over the last few bars. The raw
    # pressure formula peaks around ±0.4-0.6 at rel_vol 1.0 (0.4/0.4/0.2 weights
    # never all align at ±1), so scale ×2 to use the claimed [-1, 1] domain —
    # mirrors IMH's dominanceSensitivity multiplier.
    combined = [p * min(rv, 3.0) * 2.0 for p, rv in zip(pressures, rel_vols)]
    tail = combined[-5:]
    ema = tail[0]
    k = 2.0 / (3.0 + 1)
    for v in tail[1:]:
        ema = v * k + ema * (1 - k)
    return round(max(-1.0, min(1.0, ema)), 4)


def compute_features(
    raw_stats: dict[str, Any],
    raw_ticker: dict[str, Any],
    raw_candles_1h: list[list[Any]] | None = None,
    raw_candles_1d: list[list[Any]] | None = None,
    btc_day_change_pct: float | None = None,
    l2_snapshot: dict[str, Any] | None = None,
    btc_returns: dict[str, float] | None = None,
    raw_candles_15m: list[list[Any]] | None = None,
    raw_candles_6h: list[list[Any]] | None = None,
) -> FeatureDict:
    """Compute all features for a single symbol from raw API data."""
    # Ensure all candle inputs are sorted chronologically (oldest first)
    candles_1h = sorted(raw_candles_1h, key=lambda c: float(c[0])) if raw_candles_1h else None
    candles_15m = sorted(raw_candles_15m, key=lambda c: float(c[0])) if raw_candles_15m else None
    candles_6h = sorted(raw_candles_6h, key=lambda c: float(c[0])) if raw_candles_6h else None
    candles_1d = sorted(raw_candles_1d, key=lambda c: float(c[0])) if raw_candles_1d else None

    # Prices
    last_price = float(raw_ticker.get("price") or raw_stats.get("last") or 0.0)
    day_open = float(raw_stats.get("open") or last_price)
    day_high = float(raw_stats.get("high") or last_price)
    day_low = float(raw_stats.get("low") or last_price)

    # 24h Change %
    day_change_pct = (last_price - day_open) / day_open * 100.0 if day_open > 0 else 0.0

    # Relative Strength against BTC
    rs_vs_btc = day_change_pct - (btc_day_change_pct or 0.0)

    # Pos in range (with div-zero flat day guard)
    if day_high > day_low:
        pos_in_range = (last_price - day_low) / (day_high - day_low)
        pos_in_range = max(0.0, min(1.0, pos_in_range))
    else:
        pos_in_range = 0.5

    # Quote Volume 24h (Coinbase formula: stats.volume * last)
    base_vol = float(raw_stats.get("volume") or 0.0)
    quote_vol_24h = base_vol * last_price

    # VWAP 24h
    vwap_24h = _compute_vwap(candles_1h) if candles_1h else None
    if vwap_24h is None:
        vwap_24h = (day_high + day_low + last_price) / 3.0

    # 7d Swing metrics
    swing_shelf_7d: float | None = None
    swing_high_7d: float | None = None
    vol_7d_avg_usd: float | None = None

    if candles_1d:
        # Take up to 7 candles (most recent) from chronological list
        recent_1d = candles_1d[-7:]
        lows = [float(c[1]) for c in recent_1d if len(c) >= 6]
        highs = [float(c[2]) for c in recent_1d if len(c) >= 6]
        vols = [float(c[5]) * float(c[4]) for c in recent_1d if len(c) >= 6]

        if lows:
            swing_shelf_7d = min(lows)
        if highs:
            swing_high_7d = max(highs)
        if vols:
            vol_7d_avg_usd = sum(vols) / len(vols)

    # Macro Fib Levels (7d structural bounds)
    f_low = swing_shelf_7d if swing_shelf_7d is not None else day_low
    f_high = swing_high_7d if swing_high_7d is not None else day_high
    fibs = _fib_levels(f_low, f_high)

    # 1h RSI (Wilder's smoothing)
    rsi_1h: float | None = None
    if candles_1h:
        closes_1h = [float(c[4]) for c in candles_1h if len(c) >= 5]
        rsi_1h = _compute_rsi(closes_1h, period=14)

    # Confluence detectors (sweep / WVF / divergence) over the same 1h series.
    # Each stores bar-recency (int) or None; freshness gates live downstream so
    # the raw observation stays auditable and the windows stay tunable.
    sweep_low_bars_ago, sweep_high_bars_ago = _detect_sweeps(candles_1h)
    wvf_capitulation_bars_ago = _detect_wvf_spike(candles_1h, top_side=False)
    wvf_euphoria_bars_ago = _detect_wvf_spike(candles_1h, top_side=True)
    rsi_bull_div_bars_ago, rsi_bear_div_bars_ago = _detect_rsi_divergence(candles_1h)

    # IMH momentum-quality features (trend quality / exhaustion / pressure).
    trend_signed_imh, trend_quality_imh, trend_exhaustion_imh = _compute_trend_quality(candles_1h)
    directional_pressure_1h = _compute_directional_pressure(candles_1h)

    # RS vs BTC — multi-horizon.
    rs_vs_btc = day_change_pct - btc_day_change_pct if btc_day_change_pct is not None else 0.0

    own_returns = multi_horizon_returns(candles_1h, candles_1d)
    ret_1h = own_returns["ret_1h"]
    ret_24h = own_returns["ret_24h"]
    ret_7d = own_returns["ret_7d"]
    ret_30d = own_returns["ret_30d"]
    ret_60d = own_returns["ret_60d"]

    btc_ret = btc_returns or {}
    rs_vs_btc_1h = (
        round(ret_1h - btc_ret["ret_1h"], 4)
        if ret_1h is not None and btc_ret.get("ret_1h") is not None
        else None
    )
    rs_vs_btc_7d = (
        round(ret_7d - btc_ret["ret_7d"], 4)
        if ret_7d is not None and btc_ret.get("ret_7d") is not None
        else None
    )
    rs_vs_btc_30d = (
        round(ret_30d - btc_ret["ret_30d"], 4)
        if ret_30d is not None and btc_ret.get("ret_30d") is not None
        else None
    )
    rs_vs_btc_60d = (
        round(ret_60d - btc_ret["ret_60d"], 4)
        if ret_60d is not None and btc_ret.get("ret_60d") is not None
        else None
    )

    # 14d ATR (Average True Range)
    atr_14d: float | None = None
    if candles_1d and len(candles_1d) >= 2:
        sorted_1d = candles_1d[-15:]
        true_ranges = []
        for i in range(1, len(sorted_1d)):
            prev_c = float(sorted_1d[i - 1][4])
            h = float(sorted_1d[i][2])
            lo = float(sorted_1d[i][1])
            tr = max(h - lo, abs(h - prev_c), abs(lo - prev_c))
            true_ranges.append(tr)
        if true_ranges:
            atr_14d = sum(true_ranges[-14:]) / len(true_ranges[-14:])

    # 2% Order Book Depth Imbalance & Walls
    l2_buy_vol: float | None = None
    l2_sell_vol: float | None = None
    l2_bids: list[Any] = []
    l2_asks: list[Any] = []

    if l2_snapshot and last_price > 0:
        bids = l2_snapshot.get("bids", [])
        asks = l2_snapshot.get("asks", [])
        l2_bids = bids
        l2_asks = asks

        b_vol = sum(float(p) * float(s) for p, s, *_ in bids if float(p) >= last_price * 0.98)
        a_vol = sum(float(p) * float(s) for p, s, *_ in asks if float(p) <= last_price * 1.02)
        l2_buy_vol = round(b_vol, 2)
        l2_sell_vol = round(a_vol, 2)

    # ── Multi-Timeframe Features ──────────────────────────────────────────

    # 15m RSI
    rsi_15m: float | None = None
    if candles_15m:
        closes_15m = [float(c[4]) for c in candles_15m if len(c) >= 5]
        rsi_15m = _compute_rsi(closes_15m, period=14)

    # 6h RSI
    rsi_6h: float | None = None
    if candles_6h:
        closes_6h = [float(c[4]) for c in candles_6h if len(c) >= 5]
        rsi_6h = _compute_rsi(closes_6h, period=14)

    # 1h MACD (12, 26, 9)
    macd_1h: float | None = None
    macd_signal_1h: float | None = None
    if candles_1h:
        closes_1h_macd = [float(c[4]) for c in candles_1h if len(c) >= 5]
        macd_1h, macd_signal_1h, _ = _compute_macd(closes_1h_macd)

    # 1h Bollinger Bands (20, 2σ)
    bb_width_1h: float | None = None
    bb_pct_b_1h: float | None = None
    if candles_1h:
        closes_1h_bb = [float(c[4]) for c in candles_1h if len(c) >= 5]
        bb_width_1h, bb_pct_b_1h, _ = _compute_bollinger(closes_1h_bb)

    # 1h ATR (14-period)
    atr_1h: float | None = None
    if candles_1h and len(candles_1h) >= 15:
        atr_1h = _compute_atr(candles_1h, period=14)
        if atr_1h is not None:
            atr_1h = round(atr_1h, 6)

    # 1h Volume Ratio (current / SMA 20)
    volume_ratio_1h: float | None = None
    if candles_1h and len(candles_1h) >= 21:
        volume_ratio_1h = _compute_volume_ratio(candles_1h, lookback=20)

    # 6h EMA(50) Trend Direction
    ema_trend_6h: bool | None = None
    if candles_6h and len(candles_6h) >= 50:
        closes_6h_ema = [float(c[4]) for c in candles_6h if len(c) >= 5]
        if len(closes_6h_ema) >= 50:
            ema_50 = _compute_ema(closes_6h_ema, 50)
            ema_trend_6h = closes_6h_ema[-1] > ema_50[-1]

    return {
        "last_price": last_price,
        "day_open": day_open,
        "day_high": day_high,
        "day_low": day_low,
        "day_change_pct": round(day_change_pct, 4),
        "pos_in_range": round(pos_in_range, 4),
        "quote_vol_24h": round(quote_vol_24h, 2),
        "vwap_24h": round(vwap_24h, 6),
        "fib_236": round(fibs["fib_236"], 6),
        "fib_382": round(fibs["fib_382"], 6),
        "fib_500": round(fibs["fib_500"], 6),
        "fib_618": round(fibs["fib_618"], 6),
        "fib_786": round(fibs["fib_786"], 6),
        "rsi_1h": rsi_1h,
        "rsi_15m": rsi_15m,
        "rsi_6h": rsi_6h,
        "macd_1h": macd_1h,
        "macd_signal_1h": macd_signal_1h,
        "bb_width_1h": bb_width_1h,
        "bb_pct_b_1h": bb_pct_b_1h,
        "atr_1h": atr_1h,
        "volume_ratio_1h": volume_ratio_1h,
        "sweep_low_bars_ago": sweep_low_bars_ago,
        "sweep_high_bars_ago": sweep_high_bars_ago,
        "wvf_capitulation_bars_ago": wvf_capitulation_bars_ago,
        "wvf_euphoria_bars_ago": wvf_euphoria_bars_ago,
        "rsi_bull_div_bars_ago": rsi_bull_div_bars_ago,
        "rsi_bear_div_bars_ago": rsi_bear_div_bars_ago,
        "trend_signed_imh": trend_signed_imh,
        "trend_quality_imh": trend_quality_imh,
        "trend_exhaustion_imh": trend_exhaustion_imh,
        "directional_pressure_1h": directional_pressure_1h,
        "ema_trend_6h": ema_trend_6h,
        "rs_vs_btc": round(rs_vs_btc, 4),
        "rs_vs_btc_1h": rs_vs_btc_1h,
        "rs_vs_btc_7d": rs_vs_btc_7d,
        "rs_vs_btc_30d": rs_vs_btc_30d,
        "rs_vs_btc_60d": rs_vs_btc_60d,
        "ret_1h": ret_1h,
        "ret_24h": ret_24h,
        "ret_7d": ret_7d,
        "ret_30d": ret_30d,
        "ret_60d": ret_60d,
        "swing_shelf_7d": round(swing_shelf_7d, 6) if swing_shelf_7d is not None else None,
        "swing_high_7d": round(swing_high_7d, 6) if swing_high_7d is not None else None,
        "vol_7d_avg_usd": round(vol_7d_avg_usd, 2) if vol_7d_avg_usd is not None else None,
        "atr_14d": round(atr_14d, 6) if atr_14d is not None else None,
        "l2_buy_vol_2pct": l2_buy_vol,
        "l2_sell_vol_2pct": l2_sell_vol,
        "l2_bids": l2_bids,
        "l2_asks": l2_asks,
    }
