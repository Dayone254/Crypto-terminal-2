"""Unit tests for the labeling engine."""
from tpt.engine.labeler import compute_tags, label


def test_labeler_priority_tree() -> None:
    # 1. SKIP on low volume
    feats_low_vol = {
        "quote_vol_24h": 500_000.0,
        "day_change_pct": 20.0,
        "pos_in_range": 0.90,
        "last_price": 10.0,
        "vwap_24h": 10.0,
    }
    assert label(feats_low_vol, composite_score=80.0) == "SKIP"

    # 2. CHASE
    feats_chase = {
        "quote_vol_24h": 5_000_000.0,
        "day_change_pct": 18.0,
        "pos_in_range": 0.85,
        "last_price": 10.0,
        "vwap_24h": 10.0,
    }
    assert label(feats_chase, composite_score=75.0) == "CHASE"

    # 3. ENTRY_ZONE
    feats_entry = {
        "quote_vol_24h": 5_000_000.0,
        "day_change_pct": 4.0,
        "pos_in_range": 0.50,
        "last_price": 10.0,
        "vwap_24h": 10.0,
        "fib_500": 10.0,
        "fib_618": 9.5,
    }
    assert label(feats_entry, composite_score=65.0) == "ENTRY_ZONE"

    # 4. COILED
    feats_coiled = {
        "quote_vol_24h": 5_000_000.0,
        "day_change_pct": 1.0,
        "pos_in_range": 0.40,
        "last_price": 10.0,
        "vwap_24h": 8.0,
        "fib_500": 7.0,
        "fib_618": 6.0,
    }
    assert label(feats_coiled, composite_score=50.0) == "COILED"


def test_compute_tags() -> None:
    feats = {
        "last_price": 10.0,
        "vwap_24h": 10.0,
        "fib_500": 10.0,
        "fib_618": 9.0,
        "rsi_1h": 70.0,
    }
    tags = compute_tags(feats, pinned=True)
    assert "VWAP_CONFLUENCE" in tags
    assert "FIB50_TOUCH" in tags
    assert "OVERBOUGHT_1H" in tags
    assert "PINNED" in tags


def test_a_high_conviction_long_is_not_vetoed_by_the_macro_state() -> None:
    """Regression: a whole-cohort veto used to live in this function.

    The labeler returned SKIP for every LONG while BTC was below its short SMA
    and down on the day, regardless of the symbol's own evidence. On a live scan
    that skipped 72 of 72 longs — eleven of them scoring >=60, averaging 79.9,
    including a symbol up 73% against BTC over seven days. The macro hostility is
    now priced in the scorer; labelling must reflect the symbol, not the tape.
    """
    feats = {
        "quote_vol_24h": 10_000_000.0,
        "day_change_pct": 3.0,
        "pos_in_range": 0.50,
        "last_price": 100.0,
        "vwap_24h": 100.0,
        "fib_500": 100.0,
        "fib_618": 95.0,
    }
    assert label(feats, composite_score=75.0, trade_direction="LONG") == "ENTRY_ZONE"
    # And the low-volume floor still applies, macro state or not.
    assert label({**feats, "quote_vol_24h": 500_000.0}, composite_score=75.0) == "SKIP"
