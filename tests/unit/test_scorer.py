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

