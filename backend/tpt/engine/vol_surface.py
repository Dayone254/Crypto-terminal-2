"""
SABR Volatility Surface Smoother
=================================
Fits a SABR (Stochastic Alpha Beta Rho) model to raw venue-sourced implied
volatility observations, then interpolates smooth IV for any strike.

Benefits over raw venue IV:
- Eliminates spikes from illiquid/wide-spread strikes
- Fills gaps where venue data is missing
- Handles de-trended vol smile correctly across all strikes
- Produces a physically consistent smile (no-arbitrage constraints are respected
  by the SABR parameterisation)

Interface:
    build_vol_surface(strikes, ivs, forward, T, r) → VannaCharmSurface
    get_iv_from_surface(strike, surface, raw_iv_fallback) → float

Usage in options_flow.py:
    # Per-expiry bucket (group contracts by DTE, fit once per group)
    surface = build_vol_surface(strikes, ivs, forward, T)
    for opt in bucket:
        smoothed_iv = get_iv_from_surface(opt["strike"], surface, opt["implied_volatility"])
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import NamedTuple

import numpy as np

logger = logging.getLogger(__name__)

# Minimum number of valid IV points required to fit a SABR surface.
# Below this, we return raw IV unchanged.
_MIN_POINTS_FOR_FIT = 5

# ---------------------------------------------------------------------------
# Import pysabr — graceful fallback if missing
# ---------------------------------------------------------------------------
try:
    from pysabr import Hagan2002LognormalSABR as _SABR
    _SABR_AVAILABLE = True
    logger.info("pysabr loaded — SABR vol surface active")
except Exception as _e:
    _SABR_AVAILABLE = False
    logger.warning("pysabr unavailable (%s); SABR surface will be skipped", _e)


# ---------------------------------------------------------------------------
# Surface container
# ---------------------------------------------------------------------------

@dataclass
class VolSurface:
    """
    Fitted SABR vol surface for one expiry bucket.
    Stores fitted parameters and the original data for bounds-extrapolation.
    """
    alpha: float
    beta: float
    rho: float
    nu: float
    forward: float
    T: float
    strike_min: float
    strike_max: float
    # Fallback: raw mapping for strikes not in fitted range
    raw_map: dict[float, float]   # strike → raw IV
    # Cached SABR evaluator (set after calibration to avoid re-instantiation per lookup)
    _sabr_obj: object | None = None


def build_vol_surface(
    strikes: list[float],
    ivs: list[float],
    forward: float,
    T: float,
    beta: float = 0.5,           # Fixed β = 0.5 is a common crypto default (stochastic vol, not log-normal)
) -> VolSurface | None:
    """
    Fit a SABR surface to input (strike, IV) points.

    Parameters
    ----------
    strikes : list of floats — strike prices
    ivs     : list of floats — implied volatilities (decimal, e.g. 0.65 = 65%)
    forward : float — current forward price ≈ spot price for crypto
    T       : float — time to expiry in years
    beta    : float — SABR beta parameter (0=normal, 0.5=stochastic, 1=log-normal)

    Returns
    -------
    VolSurface or None (if fit fails or too few points)
    """
    if not _SABR_AVAILABLE:
        return None

    # Filter valid points and average IVs for duplicate strikes across exchanges
    strike_iv_map: dict[float, list[float]] = {}
    for k, iv in zip(strikes, ivs):
        if k > 0 and 0.01 <= iv <= 5.0 and forward > 0 and T > 0:
            strike_iv_map.setdefault(float(k), []).append(float(iv))

    if len(strike_iv_map) < _MIN_POINTS_FOR_FIT:
        return None

    sorted_ks = np.array(sorted(strike_iv_map.keys()), dtype=float)
    avg_vs = np.array([sum(strike_iv_map[k]) / len(strike_iv_map[k]) for k in sorted_ks], dtype=float)

    try:
        sabr = _SABR(
            beta=beta,
            f=forward,
            shift=0.0,
            t=T,
            lognormal_shift=0.0,
        )
        # Calibrate α, ρ, ν to minimise vol errors at observed strikes
        sabr.fit(sorted_ks, avg_vs)
        params = sabr.params

        surface = VolSurface(
            alpha=float(params.get("alpha", 0.5)),
            beta=beta,
            rho=float(params.get("rho", 0.0)),
            nu=float(params.get("nu", 0.5)),
            forward=forward,
            T=T,
            strike_min=float(sorted_ks.min()),
            strike_max=float(sorted_ks.max()),
            raw_map=raw_map,
        )
        # Attach the calibrated evaluator so get_iv_from_surface never needs to re-instantiate
        surface._sabr_obj = sabr
        return surface
    except Exception as exc:
        logger.debug("SABR calibration failed: %s", exc)
        return None


def get_iv_from_surface(
    strike: float,
    surface: VolSurface | None,
    raw_iv_fallback: float = 0.65,
) -> float:
    """
    Return the SABR-smoothed IV for a given strike.

    Falls back to raw_iv_fallback if:
    - surface is None (too few points or fit failed)
    - Strike is outside the fitted range
    - SABR evaluation raises an error
    """
    if surface is None:
        return raw_iv_fallback

    # Extrapolation guard — outside training range → fallback to raw IV
    if strike < surface.strike_min or strike > surface.strike_max:
        return raw_iv_fallback

    if not _SABR_AVAILABLE:
        return raw_iv_fallback

    try:
        # Use cached SABR object if available (avoids re-instantiation per lookup)
        sabr = getattr(surface, "_sabr_obj", None)
        if sabr is None:
            # Lazy rebuild for surfaces created before caching was added
            sabr = _SABR(
                beta=surface.beta,
                f=surface.forward,
                shift=0.0,
                t=surface.T,
                lognormal_shift=0.0,
            )
            sabr.alpha = surface.alpha
            sabr.rho   = surface.rho
            sabr.nu    = surface.nu
            surface._sabr_obj = sabr
        iv = float(sabr.lognormal_vol(strike))
        # Sanity check — SABR can produce garbage for extreme parametrisations
        if 0.01 <= iv <= 5.0:
            return iv
    except Exception:
        pass

    return raw_iv_fallback


# ---------------------------------------------------------------------------
# Multi-expiry surface builder
# ---------------------------------------------------------------------------

def build_surfaces_from_board(
    board: list[dict],
    spot_price: float,
    min_bucket_points: int = _MIN_POINTS_FOR_FIT,
) -> dict[str, VolSurface | None]:
    """
    Build a SABR surface per unique expiry_str from the full options board.
    Returns dict mapping expiry_str → VolSurface (or None if too sparse).
    """
    # Group by expiry
    buckets: dict[str, dict] = {}
    for opt in board:
        exp = str(opt.get("expiry_str", ""))
        if exp not in buckets:
            buckets[exp] = {"strikes": [], "ivs": []}
        iv = float(opt.get("implied_volatility", 0) or 0)
        k  = float(opt.get("strike", 0) or 0)
        if iv > 0 and k > 0:
            buckets[exp]["strikes"].append(k)
            buckets[exp]["ivs"].append(iv)

    surfaces: dict[str, VolSurface | None] = {}
    for exp, data in buckets.items():
        if len(data["strikes"]) >= min_bucket_points:
            # Approximate T from expiry_str using the same parser
            try:
                from tpt.engine.options_flow import parse_expiry
                T = parse_expiry(exp)
            except Exception:
                T = 7.0 / 365.25
            # Skip expired expiry buckets — build_vol_surface would return None anyway
            # but this avoids the overhead and makes the intent explicit.
            if T <= 0:
                surfaces[exp] = None
                continue
            surfaces[exp] = build_vol_surface(
                data["strikes"], data["ivs"], forward=spot_price, T=T
            )
        else:
            surfaces[exp] = None
    return surfaces
