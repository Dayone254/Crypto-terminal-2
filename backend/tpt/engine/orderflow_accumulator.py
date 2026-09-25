"""Orderflow Accumulator  — rolling 5-minute volume-by-price engine.

Designed to run as an always-on background coroutine fed by ws_btc_trades.
Answers: "which price levels are seeing the most real-money flow right now?"

Hot-level dict shape:
    {
        "price_level": float,       # rounded price bucket (e.g. $500 bucket)
        "volume_usd":  float,       # total USD traded in the window
        "buy_usd":     float,
        "sell_usd":    float,
        "buy_pct":     int,         # 0-100
        "sell_pct":    int,
        "trade_count": int,
        "delta_usd":   float,       # buy_usd - sell_usd (+ve = buy pressure)
    }
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque, defaultdict
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WINDOW_SECONDS   = 300      # 5-minute rolling window
BTC_BUCKET_SIZE  = 500.0    # price buckets in USD  (e.g. $500 increments)
ETH_BUCKET_SIZE  = 50.0
DEFAULT_BUCKET   = 500.0
TOP_N_LEVELS     = 5        # how many hot nodes to surface


def _bucket_size(underlying: str) -> float:
    return BTC_BUCKET_SIZE if underlying.upper() == "BTC" else (
           ETH_BUCKET_SIZE if underlying.upper() == "ETH" else DEFAULT_BUCKET)


# ---------------------------------------------------------------------------
# Per-symbol accumulator
# ---------------------------------------------------------------------------
class OrderflowAccumulator:
    """
    Maintains a deque of (ts, bucket, usd, side) tuples for one symbol.
    Thread-safe for asyncio single-event-loop use (no locks needed).
    """

    def __init__(self, underlying: str):
        self.underlying  = underlying.upper()
        self._bucket_sz  = _bucket_size(underlying)
        self._trades: deque[tuple[float, float, float, str]] = deque()
        # ts, bucket, usd, side

    def _bucket(self, price: float) -> float:
        return round(price / self._bucket_sz) * self._bucket_sz

    def add_trade(self, price: float, usd: float, side: str, ts: float | None = None) -> None:
        """Append a new trade. Automatically drops entries older than the window."""
        now    = ts or time.time()
        bucket = self._bucket(price)
        self._trades.append((now, bucket, usd, side))
        self._evict(now)

    def _evict(self, now: float) -> None:
        cutoff = now - WINDOW_SECONDS
        while self._trades and self._trades[0][0] < cutoff:
            self._trades.popleft()

    def snapshot(self) -> dict[str, Any]:
        """
        Returns a summary of the current rolling window:
          - hot_levels: top N buckets by USD volume
          - dominant_side: overall BUY or SELL
          - volume_acceleration: True if last-minute volume > avg of prior 4 minutes
          - total_volume_usd: total notional in window
        """
        now = time.time()
        self._evict(now)

        if not self._trades:
            return {"hot_levels": [], "dominant_side": "NEUTRAL",
                    "volume_acceleration": False, "total_volume_usd": 0.0}

        # Aggregate per bucket
        vol:   defaultdict[float, float] = defaultdict(float)
        buy:   defaultdict[float, float] = defaultdict(float)
        sell:  defaultdict[float, float] = defaultdict(float)
        count: defaultdict[float, int]   = defaultdict(int)

        total_buy  = 0.0
        total_sell = 0.0

        for ts, bucket, usd, side in self._trades:
            vol[bucket]   += usd
            count[bucket] += 1
            if side == "BUY":
                buy[bucket]  += usd
                total_buy    += usd
            else:
                sell[bucket] += usd
                total_sell   += usd

        total_usd = total_buy + total_sell

        # Top-N by volume
        top_buckets = sorted(vol.keys(), key=lambda b: vol[b], reverse=True)[:TOP_N_LEVELS]

        hot_levels: list[dict[str, Any]] = []
        for b in top_buckets:
            v       = vol[b]
            bv      = buy[b]
            sv      = sell[b]
            buy_pct = round((bv / v) * 100) if v > 0 else 50
            hot_levels.append({
                "price_level":  b,
                "volume_usd":   round(v, 2),
                "buy_usd":      round(bv, 2),
                "sell_usd":     round(sv, 2),
                "buy_pct":      buy_pct,
                "sell_pct":     100 - buy_pct,
                "trade_count":  count[b],
                "delta_usd":    round(bv - sv, 2),
            })

        dominant_side = "BUY" if total_buy > total_sell else ("SELL" if total_sell > total_buy else "NEUTRAL")

        # Volume acceleration: compare last 60s vs avg of prior 240s
        cutoff_1m = now - 60
        last1m    = sum(usd for ts, _, usd, _ in self._trades if ts >= cutoff_1m)
        prior4m   = sum(usd for ts, _, usd, _ in self._trades if ts < cutoff_1m)
        avg_1m_of_prior = (prior4m / 4.0) if prior4m > 0 else 0.0
        acceleration = last1m > avg_1m_of_prior * 1.25 if avg_1m_of_prior > 0 else False

        return {
            "hot_levels":          hot_levels,
            "dominant_side":       dominant_side,
            "volume_acceleration": acceleration,
            "total_volume_usd":    round(total_usd, 2),
            "window_seconds":      WINDOW_SECONDS,
        }


# ---------------------------------------------------------------------------
# Global registry  (one accumulator per underlying, shared across the app)
# ---------------------------------------------------------------------------
_accumulators: dict[str, OrderflowAccumulator] = {}


def get_accumulator(underlying: str) -> OrderflowAccumulator:
    key = underlying.upper()
    if key not in _accumulators:
        _accumulators[key] = OrderflowAccumulator(key)
    return _accumulators[key]


# ---------------------------------------------------------------------------
# Background coroutine — runs forever, feeds the accumulator
# ---------------------------------------------------------------------------
async def run_orderflow_stream(underlying: str) -> None:
    """
    Long-running coroutine: receives trades from Binance aggTrade WS and
    feeds them into the global accumulator for *underlying*.
    Should be launched as an asyncio Task.
    """
    from tpt.adapters.ws_btc_trades import stream_agg_trades
    acc = get_accumulator(underlying)
    logger.info("Orderflow stream started for %s", underlying)

    while True:
        try:
            async for trade in stream_agg_trades(underlying):
                acc.add_trade(
                    price=trade["price"],
                    usd=trade["usd"],
                    side=trade["side"],
                    ts=trade["ts"],
                )
        except asyncio.CancelledError:
            logger.info("Orderflow stream cancelled for %s", underlying)
            return
        except Exception as exc:
            logger.error("Orderflow stream error (%s): %s — restarting in 5s", underlying, exc)
            await asyncio.sleep(5)
