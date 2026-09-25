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


# ── Calibrated targets (Fix: the frozen win rate) ──────────────────────────────

def _long_feats(**overrides) -> dict:
    """A clean LONG setup: tranche A at 99, B at 95, so risk starts near 7%."""
    feats = {
        "last_price": 100.0,
        "day_high": 105.0,
        "day_low": 95.0,
        "vwap_24h": 100.0,
        "fib_500": 100.0,
        "fib_618": 98.0,
        "fib_786": 95.0,
        "swing_shelf_7d": 96.0,
        "atr_1h": 10.0,  # 10% of spot, so the ATR bound must clamp it
    }
    feats.update(overrides)
    return feats


def test_default_target_is_unchanged_at_2r() -> None:
    """With no calibration the historic 2.0R default still applies."""
    lad = compute_ladder(product_id="TEST-USD", features=_long_feats(), lbl="ENTRY_ZONE")
    assert lad is not None
    assert lad["target_r"] == 2.0
    assert abs(lad["rr_a_t1"] - 2.0) < 0.02


def test_calibrated_target_survives_sanitisation() -> None:
    """A measured target must not be forced back out to the 2.0R floor.

    `sanitize_ladder_dict` hardcoded 2.0 and so silently overrode any calibration
    — which is how the ladder kept publishing an unreachable target even after
    the ledger showed no trade had ever exceeded 0.72R.
    """
    lad = compute_ladder(
        product_id="TEST-USD", features=_long_feats(), lbl="ENTRY_ZONE", target_r=0.5
    )
    assert lad is not None
    assert lad["target_r"] == 0.5
    assert abs(lad["rr_a_t1"] - 0.5) < 0.03
    assert abs(lad["rr_a_t2"] - 1.0) < 0.05


def test_calibrated_target_below_the_rr_floor_still_publishes() -> None:
    """The 1.85R floor would reject a 0.5R target; a measurement supersedes it."""
    lad = compute_ladder(
        product_id="TEST-USD", features=_long_feats(), lbl="ENTRY_ZONE", target_r=0.5
    )
    assert lad is not None


def test_uncalibrated_0_5r_target_would_have_been_rejected() -> None:
    """Pins the floor's inverse: with no calibration the default target still
    clears 1.85R, so the floor is doing its job rather than being bypassed."""
    lad = compute_ladder(product_id="TEST-USD", features=_long_feats(), lbl="ENTRY_ZONE")
    assert lad is not None
    assert lad["rr_a_t1"] >= 1.85


# ── Risk sizing (Fix: R must mean the same on every asset) ─────────────────────

def test_risk_is_bounded_by_the_atr_band() -> None:
    """A 10% hourly ATR must not become a 17% stop, and a tiny one must not
    collapse the stop into the noise. Both clamp into [min_stop_pct, max_stop_pct]."""
    for atr in (10.0, 0.1):
        lad = compute_ladder(
            product_id="TEST-USD", features=_long_feats(atr_1h=atr), lbl="ENTRY_ZONE"
        )
        assert lad is not None
        a = lad["tranche_a_price"]
        risk_pct = abs(a - lad["stop_price"]) / a * 100.0
        assert 1.0 - 1e-6 <= risk_pct <= 3.0 + 1e-6, f"atr_1h={atr} gave {risk_pct:.2f}%"


def test_risk_falls_back_to_the_static_stop_without_atr_data() -> None:
    """No ATR means no volatility reading, so use the configured 3% rather than
    the narrowest bound — otherwise the stop lands inside the noise."""
    lad = compute_ladder(
        product_id="TEST-USD", features=_long_feats(atr_1h=0.0), lbl="ENTRY_ZONE"
    )
    assert lad is not None
    a = lad["tranche_a_price"]
    assert abs(abs(a - lad["stop_price"]) / a * 100.0 - 3.0) < 1e-6


def test_tranche_b_stays_inside_the_stop() -> None:
    """Clamping the stop inward must not leave the second entry beyond it.

    The old code moved tranche_b to the midpoint of a hardcoded 5% stop; now that
    the stop is ATR-bounded the relationship has to be maintained explicitly, or
    tranche B would be filled past invalidation.
    """
    lad = compute_ladder(
        product_id="TEST-USD", features=_long_feats(atr_1h=10.0), lbl="ENTRY_ZONE"
    )
    assert lad is not None
    assert lad["stop_price"] < lad["tranche_b_price"] < lad["tranche_a_price"]
