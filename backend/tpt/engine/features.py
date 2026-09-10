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


def compute_features(
    raw_stats: dict[str, Any],
    raw_ticker: dict[str, Any],
    raw_candles_1h: list[list[Any]] | None = None,
    raw_candles_1d: list[list[Any]] | None = None,
    btc_day_change_pct: float | None = None,
    l2_snapshot: dict[str, Any] | None = None,
    raw_candles_15m: list[list[Any]] | None = None,
    raw_candles_4h: list[list[Any]] | None = None,
) -> FeatureDict:
    """Compute all features for a single symbol from raw API data."""
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
    vwap_24h = _compute_vwap(raw_candles_1h) if raw_candles_1h else None
    if vwap_24h is None:
        vwap_24h = (day_high + day_low + last_price) / 3.0

    # 7d Swing metrics
    swing_shelf_7d: float | None = None
    swing_high_7d: float | None = None
    vol_7d_avg_usd: float | None = None

    if raw_candles_1d:
        # Take up to 7 candles (most recent)
        recent_1d = raw_candles_1d[:7]
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
    if raw_candles_1h:
        # Sort candles ascending by timestamp (c[0])
        sorted_1h = sorted(raw_candles_1h, key=lambda c: float(c[0]))
        closes_1h = [float(c[4]) for c in sorted_1h if len(c) >= 5]
        rsi_1h = _compute_rsi(closes_1h, period=14)

    # RS vs BTC
    rs_vs_btc = day_change_pct - btc_day_change_pct if btc_day_change_pct is not None else 0.0

    # (Swings moved up)

    # 14d ATR (Average True Range)
    atr_14d: float | None = None
    if raw_candles_1d and len(raw_candles_1d) >= 2:
        sorted_1d = sorted(raw_candles_1d[:15], key=lambda c: float(c[0]))
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
    if raw_candles_15m:
        sorted_15m = sorted(raw_candles_15m, key=lambda c: float(c[0]))
        closes_15m = [float(c[4]) for c in sorted_15m if len(c) >= 5]
        rsi_15m = _compute_rsi(closes_15m, period=14)

    # 4h RSI
    rsi_4h: float | None = None
    if raw_candles_4h:
        sorted_4h = sorted(raw_candles_4h, key=lambda c: float(c[0]))
        closes_4h = [float(c[4]) for c in sorted_4h if len(c) >= 5]
        rsi_4h = _compute_rsi(closes_4h, period=14)

    # 1h MACD (12, 26, 9)
    macd_1h: float | None = None
    macd_signal_1h: float | None = None
    if raw_candles_1h:
        sorted_1h_macd = sorted(raw_candles_1h, key=lambda c: float(c[0]))
        closes_1h_macd = [float(c[4]) for c in sorted_1h_macd if len(c) >= 5]
        macd_1h, macd_signal_1h, _ = _compute_macd(closes_1h_macd)

    # 1h Bollinger Bands (20, 2σ)
    bb_width_1h: float | None = None
    bb_pct_b_1h: float | None = None
    if raw_candles_1h:
        sorted_1h_bb = sorted(raw_candles_1h, key=lambda c: float(c[0]))
        closes_1h_bb = [float(c[4]) for c in sorted_1h_bb if len(c) >= 5]
        bb_width_1h, bb_pct_b_1h, _ = _compute_bollinger(closes_1h_bb)

    # 1h ATR (14-period)
    atr_1h: float | None = None
    if raw_candles_1h and len(raw_candles_1h) >= 15:
        sorted_1h_atr = sorted(raw_candles_1h, key=lambda c: float(c[0]))
        atr_1h = _compute_atr(sorted_1h_atr, period=14)
        if atr_1h is not None:
            atr_1h = round(atr_1h, 6)

    # 1h Volume Ratio (current / SMA 20)
    volume_ratio_1h: float | None = None
    if raw_candles_1h and len(raw_candles_1h) >= 21:
        sorted_1h_vol = sorted(raw_candles_1h, key=lambda c: float(c[0]))
        volume_ratio_1h = _compute_volume_ratio(sorted_1h_vol, lookback=20)

    # 4h EMA(50) Trend Direction
    ema_trend_4h: bool | None = None
    if raw_candles_4h and len(raw_candles_4h) >= 50:
        sorted_4h_ema = sorted(raw_candles_4h, key=lambda c: float(c[0]))
        closes_4h_ema = [float(c[4]) for c in sorted_4h_ema if len(c) >= 5]
        if len(closes_4h_ema) >= 50:
            ema_50 = _compute_ema(closes_4h_ema, 50)
            ema_trend_4h = closes_4h_ema[-1] > ema_50[-1]

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
        "rsi_4h": rsi_4h,
        "macd_1h": macd_1h,
        "macd_signal_1h": macd_signal_1h,
        "bb_width_1h": bb_width_1h,
        "bb_pct_b_1h": bb_pct_b_1h,
        "atr_1h": atr_1h,
        "volume_ratio_1h": volume_ratio_1h,
        "ema_trend_4h": ema_trend_4h,
        "rs_vs_btc": round(rs_vs_btc, 4),
        "swing_shelf_7d": round(swing_shelf_7d, 6) if swing_shelf_7d is not None else None,
        "swing_high_7d": round(swing_high_7d, 6) if swing_high_7d is not None else None,
        "vol_7d_avg_usd": round(vol_7d_avg_usd, 2) if vol_7d_avg_usd is not None else None,
        "atr_14d": round(atr_14d, 6) if atr_14d is not None else None,
        "l2_buy_vol_2pct": l2_buy_vol,
        "l2_sell_vol_2pct": l2_sell_vol,
        "l2_bids": l2_bids,
        "l2_asks": l2_asks,
    }
