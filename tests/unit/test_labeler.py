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
