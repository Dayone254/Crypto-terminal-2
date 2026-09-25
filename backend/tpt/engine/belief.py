"""Belief state — how much the score knows, and how far it should be trusted.

`scorer.score()` emits a single number, but two different things produce it:
the weighted evidence a symbol actually has, and how much of the model that
evidence *covers*. Collapsing those into one number hides the difference between
"this setup is bad" and "we never looked" — which is precisely the failure this
module exists to make visible.

The three quantities
--------------------
``edge``
    Directional conviction in [-1, 1] normalised to [0, 100], computed as a
    weighted mean over *backed* components only. Because it is renormalised, it
    is comparable between two symbols that were fed different amounts of data.
``coverage``
    The share of the model's weight that real observations back, in [0, 1].
    ``coverage == 1.0`` means every component had data; ``0.55`` means 45% of the
    model was silent for this symbol.
``rank_key``
    What the brain should actually be ranked by: ``edge`` shrunk toward neutral
    in proportion to how little is known, plus evidence-scaled interactions. A
    symbol the brain barely looked at cannot outrank one it examined closely.

Shrinkage is not a penalty bolted on. A zero-filled weighted sum *is* shrinkage
toward neutral — `sum(available w_i * x_i) == edge_norm * coverage` — so
``rank_key`` reduces exactly to the historical ``base_calc`` when no interactions
fire. What was missing was never the arithmetic; it was naming the two numbers
separately so a low-coverage score could not masquerade as a high-conviction one.

Pure functions. No I/O.
"""
from __future__ import annotations

from typing import Any

FeatureDict = dict[str, Any]

# Bump when the meaning of any input changes, so a stored feature vector can be
# interpreted against the definition it was actually produced under.
FEATURE_VERSION = "fv2"

# Which raw feature backs each weighted component. A component counts as backed
# only when its source was genuinely observed: a missing source must shrink the
# score, never silently contribute a zero as though it were a real reading.
_SOURCES: dict[str, dict[str, str]] = {
    "LONG": {
        "liquidity": "quote_vol_24h",
        "trend_strength": "day_change_pct",
        "relative_strength": "rs_vs_btc_7d",
        "volatility_compression": "bb_width_1h",
        "momentum": "rsi_1h",
        "l2_support": "l2_buy_vol_2pct",
    },
    "SHORT": {
        "liquidity": "quote_vol_24h",
        "trend_weakness": "day_change_pct",
        "relative_weakness": "rs_vs_btc_7d",
        "volatility_expansion": "bb_width_1h",
        "momentum": "rsi_1h",
        "l2_resistance": "l2_sell_vol_2pct",
    },
}

# For these sources a zero is indistinguishable from "no data" and must be read
# as missing. `stats.volume` absent yields quote_vol_24h == 0.0, which otherwise
# normalises to a phantom -1.0 penalty on liquidity.
_ZERO_IS_MISSING = frozenset({"quote_vol_24h"})

# The exact inputs the scorer reads. Stored per symbol so a score can be
# replayed, audited and retrained against later — see `serialize_feature_vector`.
SCORER_INPUTS: tuple[str, ...] = (
    "quote_vol_24h",
    "day_change_pct",
    "pos_in_range",
    "rsi_1h",
    "rsi_15m",
    "rsi_6h",
    "bb_width_1h",
    "bb_pct_b_1h",
    "volume_ratio_1h",
    "macd_1h",
    "atr_1h",
    "atr_14d",
    "ema_trend_6h",
    "rs_vs_btc",
    "rs_vs_btc_1h",
    "rs_vs_btc_7d",
    "ret_1h",
    "ret_24h",
    "ret_7d",
    "last_price",
    "day_open",
    "day_high",
    "day_low",
    "vwap_24h",
    "fib_236",
    "fib_382",
    "fib_500",
    "fib_618",
    "fib_786",
    "swing_shelf_7d",
    "swing_high_7d",
    "l2_buy_vol_2pct",
    "l2_sell_vol_2pct",
    "funding_rate",
    "oi_change_pct",
)


def availability(features: FeatureDict, direction: str) -> dict[str, bool]:
    """Report, per weighted component, whether a real observation backs it."""
    sources = _SOURCES.get(direction, _SOURCES["LONG"])
    backed: dict[str, bool] = {}
    for component, source in sources.items():
        value = features.get(source)
        # A source that is absent, or one whose zero is indistinguishable from
        # "no data", cannot back a component — the score must shrink instead.
        backed[component] = not (
            value is None or (source in _ZERO_IS_MISSING and float(value) <= 0.0)
        )
    return backed


def edge_and_coverage(
    norm: dict[str, float],
    weights: dict[str, float],
    backed: dict[str, bool],
) -> tuple[float, float, float]:
    """Return ``(edge_norm, edge, coverage)``.

    ``edge_norm`` is the weighted mean of the backed normalised features, so it
    answers "how good is what we saw" independently of how much we saw.
    ``coverage`` is the total weight those backed components carry.
    ``edge`` rescales ``edge_norm`` onto the 0-100 display range.
    """
    numerator = 0.0
    denominator = 0.0
    for component, weight in weights.items():
        if backed.get(component, False):
            numerator += norm.get(component, 0.0) * weight
            denominator += weight

    coverage = denominator
    edge_norm = (numerator / denominator) if denominator > 0.0 else 0.0
    edge = 50.0 + 50.0 * edge_norm
    return edge_norm, edge, coverage


def shrink_interactions(
    feature_interactions: float,
    macro_interactions: float,
    coverage: float,
) -> float:
    """Trust interactions in proportion to the evidence behind them.

    Interactions read off the symbol's own features (confluence, breakout,
    relative-strength bonus) are conclusions drawn from that symbol's data, so
    they shrink with its ``coverage``. Macro interactions — regime, funding,
    dealer gamma — come from an independent feed and only fire when that feed
    actually delivered, so they are already self-gating and are left alone.
    """
    return feature_interactions * coverage + macro_interactions


def rank_key(
    edge_norm: float,
    coverage: float,
    interactions: float = 0.0,
    baseline: float = 50.0,
) -> float:
    """The quantity to rank by: edge, shrunk toward neutral by coverage."""
    return baseline + 50.0 * edge_norm * coverage + interactions


def serialize_feature_vector(features: FeatureDict) -> dict[str, Any]:
    """The scorer's inputs, verbatim, minus the raw order book.

    ``l2_bids``/``l2_asks`` are excluded because they are thousands of levels
    wide; their derived totals (``l2_buy_vol_2pct``) are what the brain reads.
    """
    vector: dict[str, Any] = {}
    for key in SCORER_INPUTS:
        if key in features:
            value = features[key]
            if isinstance(value, (bool, int, float)) or value is None:
                vector[key] = value
            else:
                vector[key] = str(value)
    return vector


def coverage_band(coverage: float) -> str:
    """Coarse label for display, so a score carries its own confidence."""
    if coverage >= 0.85:
        return "FULL"
    if coverage >= 0.60:
        return "PARTIAL"
    if coverage > 0.0:
        return "THIN"
    return "BLIND"
