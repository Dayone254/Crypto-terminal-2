"""Unit tests for the ladder computation engine."""
from tpt.engine.ladder import compute_ladder


def test_ladder_suppressed_on_chase() -> None:
    feats = {"last_price": 10.0, "day_high": 12.0}
    assert compute_ladder(product_id="TEST-USD", features=feats, lbl="CHASE") is None
    assert compute_ladder(product_id="TEST-USD", features=feats, lbl="SKIP") is None


def test_ladder_suppressed_on_unpinned_watch() -> None:
    feats = {"last_price": 10.0, "day_high": 12.0}
    assert compute_ladder(product_id="TEST-USD", features=feats, lbl="WATCH", pinned=False) is None


def test_ladder_generated_on_entry_zone() -> None:
    feats = {
        "last_price": 10.0,
        "day_high": 12.0,
        "vwap_24h": 9.9,
        "fib_500": 9.8,
        "fib_618": 9.4,
        "fib_786": 8.8,
        "swing_shelf_7d": 8.5,
        "swing_high_7d": 13.0,
    }
    lad = compute_ladder(product_id="TEST-USD", features=feats, lbl="ENTRY_ZONE")
    assert lad is not None
    assert lad["tranche_a_price"] < 10.0
    assert lad["tranche_b_price"] < lad["tranche_a_price"]
    assert lad["stop_price"] < lad["tranche_b_price"]
    assert lad["target_1_price"] > lad["tranche_a_price"]
    assert lad["target_2_price"] >= lad["target_1_price"]
    assert lad["rr_a_t1"] > 0
