"""Tests for the institutional gamma analytics layer.

All pure functions — no network, no DB. Ground-truth values are constructed
by hand so each test pins real math, not implementation echoes.
"""

import pytest

from tpt.engine.gamma_analytics import (
    GammaRegimeTracker,
    compute_confidence,
    compute_expiry_clusters,
    compute_hedging_profile,
    compute_max_pain,
    compute_pin_map,
    compute_skew_metrics,
)


# ─── MAX PAIN ──────────────────────────────────────────────────────────────

def test_max_pain_basic_asymmetry():
    # Calls stacked at 95 (30 OI), puts at 105 (10 OI) → max pain at 95:
    # pain(95) = 10×(105−95) = 100 < pain(105) = 30×(105−95) = 300.
    pain = compute_max_pain({95.0: 30.0}, {105.0: 10.0}, spot=100.0)
    assert pain == 95.0


def test_max_pain_empty_board():
    assert compute_max_pain({}, {}, spot=100.0) is None


def test_max_pain_tiebreaks_toward_spot():
    # Symmetric pain at 95 and 105 → the magnet nearer spot wins.
    pain = compute_max_pain({95.0: 10.0}, {105.0: 10.0}, spot=104.0)
    assert pain == 105.0


# ─── SKEW (RR25 / Fly25) ──────────────────────────────────────────────────

def _skew_board():
    opts = []
    for k, iv in ((90.0, 0.70), (95.0, 0.68)):
        opts.append({"expiry_str": "7D", "strike": k, "type": "P",
                     "implied_volatility": iv, "open_interest": 100.0})
    for k, iv in ((105.0, 0.60), (110.0, 0.58)):
        opts.append({"expiry_str": "7D", "strike": k, "type": "C",
                     "implied_volatility": iv, "open_interest": 100.0})
    for k, iv in ((100.0, 0.62),):
        opts.append({"expiry_str": "7D", "strike": k, "type": "C",
                     "implied_volatility": iv, "open_interest": 100.0})
        opts.append({"expiry_str": "7D", "strike": k, "type": "P",
                     "implied_volatility": iv, "open_interest": 100.0})
    return opts


def test_skew_flags_put_skew_as_negative_rr25():
    res = compute_skew_metrics(_skew_board(), spot=100.0)
    assert res is not None
    assert res["ref_expiry"] == "7D"
    # Put wing IV (0.70/0.68) exceeds call wing IV (0.60/0.58) → RR25 < 0.
    assert res["rr25_pct"] < 0
    # Wings average well above ATM → positive butterfly.
    assert res["fly25_pct"] > 0


def test_skew_needs_two_sided_chain():
    one_sided = [{"expiry_str": "7D", "strike": 105.0, "type": "C",
                  "implied_volatility": 0.6, "open_interest": 10.0}]
    assert compute_skew_metrics(one_sided, spot=100.0) is None


# ─── EXPIRY CLUSTERS ──────────────────────────────────────────────────────

def test_expiry_clusters_ranking_and_zero_dte_share():
    board = [
        {"expiry_str": "25DEC26", "strike": 100.0, "type": "C", "open_interest": 900.0, "underlying_price": 100.0},
        {"expiry_str": "30OCT26", "strike": 100.0, "type": "P", "open_interest": 100.0, "underlying_price": 100.0},
        {"expiry_str": "1D", "strike": 100.0, "type": "C", "open_interest": 400.0, "underlying_price": 100.0},
    ]
    clusters = compute_expiry_clusters(board)
    assert clusters[0]["expiry"] == "25DEC26"
    shares = [c["share_pct"] for c in clusters if c["expiry"] != "_0DTE_SHARE"]
    assert abs(sum(shares) - 100.0) < 0.5
    z = next(c for c in clusters if c["expiry"] == "_0DTE_SHARE")
    # 400 of 1400 total ≈ 28.6%.
    assert z["share_pct"] == pytest.approx(28.6, abs=0.2)


# ─── HEDGING PROFILE ──────────────────────────────────────────────────────

def test_hedging_profile_supportive_bias():
    gex = {95.0: 5e8, 105.0: -3e8, 120.0: -1e9}  # 120 is outside the ±5% band
    res = compute_hedging_profile(gex, spot=100.0)
    assert res["bias"] == "SUPPORTIVE"
    assert res["downside_support_gex_m"] == pytest.approx(500.0)
    assert res["upside_resistance_gex_m"] == pytest.approx(300.0)
    assert res["top_supportive"][0]["strike"] == 95.0
    assert res["top_suppressive"][0]["strike"] == 105.0
    # Out-of-band strike must NOT appear anywhere.
    assert all(s["strike"] != 120.0 for s in res["top_suppressive"])


def test_hedging_profile_suppressive_and_empty():
    res = compute_hedging_profile({105.0: -6e8}, spot=100.0)
    assert res["bias"] == "SUPPRESSIVE"
    assert compute_hedging_profile({}, spot=100.0)["bias"] == "NEUTRAL"


# ─── PIN MAP ──────────────────────────────────────────────────────────────

def test_pin_map_weights_distance_and_excludes_negatives():
    gex = {
        100.5: 2e8,    # closest positive → strongest pin
        104.0: 8e8,    # big gamma, further away
        96.0: -5e8,    # negative gamma → repels, excluded
        115.0: 9e8,    # >10% away → excluded
    }
    pins = compute_pin_map(gex, spot=100.0, max_pins=3)
    strikes = [p["strike"] for p in pins]
    assert 100.5 in strikes and 104.0 in strikes
    assert 96.0 not in strikes and 115.0 not in strikes
    assert pins[0]["strike"] == 100.5
    assert pins[0]["strength"] == 100.0


# ─── CONFIDENCE ───────────────────────────────────────────────────────────

def test_confidence_grades_full_board_as_a():
    board = [{"strike": i, "open_interest": 10.0, "underlying_price": 100.0} for i in range(250)]
    venues = {"active_venues": ["Deribit", "Binance", "OKX", "Bybit"],
              "total_open_interest_usd": 5e9}
    res = compute_confidence(board, venues, spot=100.0, vol_surface_fitted=True)
    assert res["grade"] == "A"
    assert res["score"] >= 95


def test_confidence_empty_board_is_f():
    res = compute_confidence([], {"active_venues": [], "total_open_interest_usd": 0},
                             spot=0.0, vol_surface_fitted=False)
    assert res["score"] <= 10
    assert res["grade"] in ("D", "F")
    assert any("no venues" in r for r in res["reasons"])


# ─── REGIME TRACKER (flip confirmation) ──────────────────────────────────

def test_flip_requires_hold_window():
    t = GammaRegimeTracker(min_hold_seconds=600.0)
    # Establish LONG.
    assert t.observe("BTC", "LONG_GAMMA_STABLE", 100.0, now=0.0) is None
    # Single SHORT observation → candidate only, no flip.
    assert t.observe("BTC", "SHORT_GAMMA_VOLATILE", 100.0, now=10.0) is None
    # SHORT held past the window → flip fires.
    flip = t.observe("BTC", "SHORT_GAMMA_VOLATILE", 99.0, now=700.0)
    assert flip is not None
    assert flip["from"] == "LONG_GAMMA_STABLE"
    assert flip["to"] == "SHORT_GAMMA_VOLATILE"
    assert t.transitions("BTC")[-1]["ts"] == 700.0


def test_flapping_never_confirms():
    t = GammaRegimeTracker(min_hold_seconds=600.0)
    assert t.observe("ETH", "LONG_GAMMA_STABLE", 100.0, now=0.0) is None
    # Alternate every 100s — candidate resets each time, no flip ever.
    for i in range(1, 12):
        regime = "SHORT_GAMMA_VOLATILE" if i % 2 else "LONG_GAMMA_STABLE"
        assert t.observe("ETH", regime, 100.0, now=i * 100.0) is None
    assert t.transitions("ETH") == []
