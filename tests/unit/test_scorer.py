"""Unit tests for the scoring engine."""
from tpt.engine.scorer import score


def test_scorer_baseline_and_normalization() -> None:
    feats = {
        "last_price": 100.0,
        "day_change_pct": 0.0,
        "pos_in_range": 0.50,
        "quote_vol_24h": 3_000_000.0,
        "vwap_24h": 100.0,
        "rsi_1h": 50.0,
        "rs_vs_btc": 0.0,
        "fib_500": 95.0,
        "fib_618": 90.0,
    }
    s = score(feats)
    assert s["baseline"] == 50
    assert "liquidity" in s["components"]

    # Liquidity band (V3.1): $1M floor -> 0.0, $5M+ -> 1.0, linear between.
    # $3M -> (3M - 1M) / 4M = 0.5
    assert abs(s["components"]["liquidity"] - 0.5) < 0.01

    assert s["interactions"] == 0.0
    assert 0.0 <= s["clamped"] <= 100.0


def test_scorer_liquidity_band_edges() -> None:
    """Pin the documented liquidity normalisation: $1M -> 0.0, $5M+ -> 1.0."""
    base = {
        "last_price": 100.0,
        "day_change_pct": 0.0,
        "pos_in_range": 0.50,
        "vwap_24h": 100.0,
        "rsi_1h": 50.0,
        "rs_vs_btc": 0.0,
        "fib_500": 95.0,
        "fib_618": 90.0,
    }
    at_floor = score({**base, "quote_vol_24h": 1_000_000.0})
    assert abs(at_floor["components"]["liquidity"] - 0.0) < 0.01

    at_ceiling = score({**base, "quote_vol_24h": 5_000_000.0})
    assert abs(at_ceiling["components"]["liquidity"] - 1.0) < 0.01


def test_scorer_interactive_confluence_bonus() -> None:
    # Setup for an oversold bounce near Fib 50%
    feats = {
        "last_price": 10.0,
        "day_change_pct": -5.0,
        "pos_in_range": 0.20,
        "quote_vol_24h": 10_000_000.0,
        "rsi_1h": 35.0,      # Oversold (< 40)
        "fib_500": 10.0,     # Right on Fib 50%
        "rs_vs_btc": 4.0,
    }
    # Oversold AND fib confluence should trigger interaction bonus
    s = score(feats, trade_direction="LONG")
    
    assert s["components"]["rsi_oversold"] >= 1.0
    assert s["components"]["fib_confluence"] >= 1.0
    assert s["interactions"] > 0.0  # Confluence bonus triggered
    assert s["clamped"] > 0.0


def test_scorer_regime_modifier() -> None:
    # Fighting the trend should penalize
    feats = {
        "last_price": 10.0,
        "day_change_pct": 2.0,  # Positive day change -> trend_aligned = 1 for LONG, 0 for SHORT
    }
    
    # Shorting during a TRENDING_UP regime is fighting the trend
    s_short = score(feats, trade_direction="SHORT", regime="TRENDING_UP")
    assert s_short["components"]["trend_aligned"] == 0.0
    assert s_short["interactions"] < 0.0  # Counter-trend penalty


def _strong_long_features(rs_7d: float) -> dict:
    """A fully-observed LONG setup: all six components backed, coverage 1.00."""
    return {
        "last_price": 100.0,
        "day_change_pct": 3.0,
        "pos_in_range": 0.50,
        "quote_vol_24h": 10_000_000.0,
        "vwap_24h": 100.0,
        "rsi_1h": 55.0,
        "bb_width_1h": 0.05,
        "rs_vs_btc_7d": rs_7d,
        "fib_500": 100.0,
        "fib_618": 95.0,
        "l2_buy_vol_2pct": 300_000.0,
    }


def test_macro_beta_headwind_is_priced_not_vetoed() -> None:
    """The behaviour that replaced the hard SKIP.

    The labeler used to return SKIP for every LONG whenever BTC was dumping,
    which on a live scan silently discarded all 72 longs — eleven of them scoring
    >=60 and averaging 79.9. The hostility is now a penalty in proportion to its
    magnitude, so an exceptional setup can still clear the entry gate while a
    marginal one still cannot.
    """
    feats = _strong_long_features(rs_7d=30.0)

    calm = score(feats, trade_direction="LONG", macro_thrust=0.0)
    dump = score(feats, trade_direction="LONG", macro_thrust=-3.0)

    # Full coverage: every component had real data.
    assert calm["coverage"] == 1.0
    # Hostile tape costs points ...
    assert dump["clamped"] < calm["clamped"]
    assert dump["components"]["macro_beta_headwind"] < 0
    # ... exactly the configured maximum at full headwind.
    assert abs(calm["clamped"] - dump["clamped"] - 18.0) < 0.01
    # ... but the strongest relative performer still clears the entry gate.
    assert dump["clamped"] >= 60.0


def test_macro_beta_headwind_saturates_and_scales() -> None:
    feats = _strong_long_features(rs_7d=30.0)
    half = score(feats, trade_direction="LONG", macro_thrust=-1.5)   # half of 3%
    full = score(feats, trade_direction="LONG", macro_thrust=-3.0)   # saturates
    beyond = score(feats, trade_direction="LONG", macro_thrust=-9.0)  # no further cost
    assert abs(full["clamped"] - beyond["clamped"]) < 1e-9
    assert half["clamped"] > full["clamped"]
    assert abs((half["clamped"] - full["clamped"]) - 9.0) < 0.01


def test_a_marginal_long_still_cannot_enter_a_dump() -> None:
    """The other half of the guarantee: pricing must not mean waving things through."""
    weak = _strong_long_features(rs_7d=3.0)
    dump = score(weak, trade_direction="LONG", macro_thrust=-3.0)
    assert dump["clamped"] < 60.0


def test_tailwind_is_not_penalised() -> None:
    """A rising tape must not punish a long — the term is one-sided."""
    feats = _strong_long_features(rs_7d=30.0)
    calm = score(feats, trade_direction="LONG", macro_thrust=0.0)
    up = score(feats, trade_direction="LONG", macro_thrust=+3.0)
    assert "macro_beta_headwind" not in up["components"]
    assert abs(up["clamped"] - calm["clamped"]) < 1e-9

