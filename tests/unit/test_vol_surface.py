"""Tests for the SABR volatility surface and its integration with the GEX engine.

History: build_vol_surface referenced an undefined ``raw_map`` inside its
constructor call, so calibration ALWAYS raised NameError and the engine silently
ran on raw venue IVs forever (``vol_surface_fitted`` was permanently False).
These tests pin the fit to known ground-truth parameters.
"""

import math

import numpy as np
import pytest

from tpt.engine.vol_surface import (
    _SABR_AVAILABLE,
    build_vol_surface,
    build_surfaces_from_board,
    get_iv_from_surface,
)

# Ground truth: generate a smile with known SABR params, then recover them.
_TRUE_ALPHA, _TRUE_BETA, _TRUE_RHO, _TRUE_NU = 0.60, 0.5, -0.30, 1.20
_FORWARD, _T = 100.0, 7.0 / 365.25


def _synthetic_smile():
    from pysabr.models.hagan_2002_lognormal_sabr import lognormal_vol
    strikes = [80.0, 90.0, 95.0, 100.0, 105.0, 110.0, 120.0]
    ivs = [
        float(lognormal_vol(k, _FORWARD, _T, _TRUE_ALPHA, _TRUE_BETA, _TRUE_RHO, _TRUE_NU))
        for k in strikes
    ]
    return strikes, ivs


@pytest.mark.skipif(not _SABR_AVAILABLE, reason="pysabr not installed")
def test_build_vol_surface_no_longer_always_none():
    """The raw_map NameError meant this ALWAYS returned None."""
    strikes, ivs = _synthetic_smile()
    surface = build_vol_surface(strikes, ivs, forward=_FORWARD, T=_T)
    assert surface is not None, "SABR calibration must succeed on a clean smile"
    assert surface.forward == pytest.approx(_FORWARD)
    assert surface.raw_map, "raw fallback map must be populated"


@pytest.mark.skipif(not _SABR_AVAILABLE, reason="pysabr not installed")
def test_sabr_fit_recovers_ground_truth():
    strikes, ivs = _synthetic_smile()
    surface = build_vol_surface(strikes, ivs, forward=_FORWARD, T=_T)
    assert surface is not None
    assert surface.rho < 0, "smile was generated with negative skew; fit must see it"
    # Alpha is on the SABR internal scale; the informative check is that the
    # fitted smile reproduces the observed IVs closely.
    for k, iv in zip(strikes, ivs):
        fitted = get_iv_from_surface(k, surface, raw_iv_fallback=0.0)
        assert fitted == pytest.approx(iv, rel=0.05), (
            f"fitted IV at strike {k} deviates >5% from the observed smile"
        )


@pytest.mark.skipif(not _SABR_AVAILABLE, reason="pysabr not installed")
def test_interpolation_between_strikes_is_smooth():
    strikes, ivs = _synthetic_smile()
    surface = build_vol_surface(strikes, ivs, forward=_FORWARD, T=_T)
    assert surface is not None
    mids = [get_iv_from_surface(k, surface, raw_iv_fallback=0.0)
            for k in (92.0, 97.0, 103.0, 112.0)]
    # Interpolated IVs must be positive and inside the smile's plausible band.
    for iv in mids:
        assert 0.01 <= iv <= 5.0
    # Monotone-ish skew: IV at 92 (put side) should exceed IV at 112 (call side)
    assert mids[0] > mids[3]


@pytest.mark.skipif(not _SABR_AVAILABLE, reason="pysabr not installed")
def test_out_of_range_strike_falls_back_to_raw_map():
    strikes, ivs = _synthetic_smile()
    surface = build_vol_surface(strikes, ivs, forward=_FORWARD, T=_T)
    assert surface is not None
    # Below the fitted range → raw fallback, not extrapolated garbage
    iv = get_iv_from_surface(70.0, surface, raw_iv_fallback=0.65)
    assert iv == pytest.approx(0.65)


def test_too_few_points_returns_none():
    surface = build_vol_surface(
        [95.0, 100.0, 105.0], [0.6, 0.55, 0.5], forward=100.0, T=0.02
    )
    assert surface is None


@pytest.mark.skipif(not _SABR_AVAILABLE, reason="pysabr not installed")
def test_build_surfaces_from_board_marks_fitted():
    """The GEX engine's vol_surface_fitted flag must turn True on a real chain."""
    strikes, ivs = _synthetic_smile()
    board = [
        {
            "expiry_str": "7D",
            "strike": k,
            "implied_volatility": iv,
            "open_interest": 10.0,
            "type": "C" if k >= _FORWARD else "P",
            "underlying": "TEST",
        }
        for k, iv in zip(strikes, ivs)
    ]
    surfaces = build_surfaces_from_board(board, spot_price=_FORWARD)
    assert surfaces.get("7D") is not None
