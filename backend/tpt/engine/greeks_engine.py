"""
Greeks Engine — Institutional-Grade Black-Scholes Implementation
================================================================
Uses `py_vollib_vectorized` (Jaeckel's 'Let's Be Rational' IV + Numba JIT)
for batch computation of Delta, Gamma, Vega, Theta, Vanna, and Charm.

All output conventions:
  - Delta:  [0, 1] for calls,  [-1, 0] for puts
  - Gamma:  always positive, units: 1/(price × vol × √T)
  - Vega:   per 1pp move in IV (already /100)
  - Theta:  per calendar day (already /365)
  - Vanna:  ∂Δ/∂σ — sensitivity of delta to vol shift (per unit of σ)
  - Charm:  ∂Δ/∂t — delta bleed per calendar day (per day, /365)
"""
from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Try to use the vectorized batch engine; fall back to scalar Python on error
# ---------------------------------------------------------------------------
try:
    from scipy.special import erf as _scipy_erf  # type: ignore[import-untyped,import-not-found]
    _SCIPY_ERF_AVAILABLE = True
except Exception:
    _SCIPY_ERF_AVAILABLE = False


try:
    from py_vollib_vectorized import vectorized_implied_volatility as _vec_iv
    from py_vollib_vectorized import (
        vectorized_delta as _vec_delta,
        vectorized_gamma as _vec_gamma,
        vectorized_theta as _vec_theta,
        vectorized_vega  as _vec_vega,
    )
    _VECTORIZED_AVAILABLE = True
    logger.info("py_vollib_vectorized loaded — batch Greek computation active")
except Exception as _e:
    _VECTORIZED_AVAILABLE = False
    logger.warning("py_vollib_vectorized unavailable (%s); using scalar fallback", _e)



# ---------------------------------------------------------------------------
# Low-level scalar helpers (always available as fallback)
# ---------------------------------------------------------------------------

def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x**2) / math.sqrt(2.0 * math.pi)

def _d1d2(S: float, K: float, T: float, r: float, sigma: float):
    if T <= 0 or sigma <= 0:
        return 0.0, 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return d1, d2


# ---------------------------------------------------------------------------
# Scalar Greek computation (used as fallback and for single-contract calls)
# ---------------------------------------------------------------------------

def compute_greeks(
    S: float, K: float, T: float, r: float, sigma: float,
    option_type: str = "C",
) -> dict[str, float]:
    """
    Compute Delta, Gamma, Vega, Theta, Vanna, Charm for a single option.

    Returns dict with all six Greeks. Vanna and Charm are new additions.
    """
    if T <= 0.0001 or sigma <= 0 or S <= 0 or K <= 0:
        return {"delta": 0.0, "gamma": 0.0, "theta": 0.0,
                "vega": 0.0, "vanna": 0.0, "charm": 0.0}

    d1, d2 = _d1d2(S, K, T, r, sigma)
    is_call = option_type.upper() in ("C", "CALL")
    npdf_d1 = norm_pdf(d1)

    # ── Core Greeks ─────────────────────────────────────────────────────────
    delta = norm_cdf(d1) if is_call else norm_cdf(d1) - 1.0
    gamma = npdf_d1 / (S * sigma * math.sqrt(T))
    vega  = S * npdf_d1 * math.sqrt(T) / 100.0   # per 1pp IV move

    term1 = -(S * npdf_d1 * sigma) / (2.0 * math.sqrt(T))
    if is_call:
        theta = (term1 - r * K * math.exp(-r * T) * norm_cdf(d2)) / 365.0
    else:
        theta = (term1 + r * K * math.exp(-r * T) * norm_cdf(-d2)) / 365.0

    # ── 2nd-Order Greeks ────────────────────────────────────────────────────
    # Vanna = ∂Δ/∂σ = -N'(d1) × d2 / σ
    # Economic meaning: how much dealer delta changes when IV moves 1 unit.
    # A positive vanna regime (IV rising + OTM calls) forces extra spot buying.
    vanna = -npdf_d1 * d2 / sigma

    # Charm = ∂Δ/∂t (delta bleed per calendar day)
    # Economic meaning: how much dealer delta changes with each day of passage.
    # Important for 0DTE risk and weekend hedging dynamics.
    if is_call:
        charm = -npdf_d1 * (r / (sigma * math.sqrt(T)) - d2 / (2.0 * T)) / 365.0
    else:
        charm = -npdf_d1 * (r / (sigma * math.sqrt(T)) - d2 / (2.0 * T)) / 365.0
        # Put charm: same formula (charm is same sign as call for dealer perspective)

    return {
        "delta": delta,
        "gamma": gamma,
        "theta": theta,
        "vega":  vega,
        "vanna": vanna,
        "charm": charm,
    }


# ---------------------------------------------------------------------------
# Batch vectorized computation (main path when py_vollib_vectorized is present)
# ---------------------------------------------------------------------------

def compute_greeks_batch(
    spots:   np.ndarray,   # S — current underlying price for each contract
    strikes: np.ndarray,   # K — strike price
    times:   np.ndarray,   # T — time to expiry in years
    rates:   np.ndarray,   # r — risk-free rate
    sigmas:  np.ndarray,   # σ — implied volatility (decimal)
    flags:   list[str],    # 'c' = call, 'p' = put (py_vollib convention)
) -> dict[str, np.ndarray]:
    """
    Batch compute Greeks for N contracts simultaneously using the JIT-compiled engine.
    Returns dict of arrays: delta, gamma, theta, vega, vanna, charm.

    Falls back to scalar loop if the vectorized engine is unavailable.
    """
    n = len(spots)
    if n == 0:
        empty = np.array([], dtype=float)
        return {"delta": empty, "gamma": empty, "theta": empty,
                "vega": empty, "vanna": empty, "charm": empty}

    try:
        # Analytical NumPy vectorized Black-Scholes equations
        # Gives sub-millisecond calculation across all contracts without Numba type-inference overhead
        safe_sigmas = np.maximum(sigmas, 1e-6)
        safe_spots  = np.maximum(spots, 1e-8)
        safe_strikes = np.maximum(strikes, 1e-8)

        is_call_arr = (np.array(flags) == 'c')
        sqrt_t = np.sqrt(np.maximum(times, 1e-8))
        d1 = (np.log(safe_spots / safe_strikes) + (rates + 0.5 * safe_sigmas**2) * times) / (safe_sigmas * sqrt_t)
        d2 = d1 - safe_sigmas * sqrt_t
        npdf_d1 = np.exp(-0.5 * d1**2) / math.sqrt(2.0 * math.pi)

        if _SCIPY_ERF_AVAILABLE:
            erf_fn = _scipy_erf
        else:
            erf_fn = np.vectorize(math.erf)

        ncdf_d1 = 0.5 * (1.0 + erf_fn(d1 / math.sqrt(2.0)))
        ncdf_d2 = 0.5 * (1.0 + erf_fn(d2 / math.sqrt(2.0)))
        ncdf_neg_d2 = 0.5 * (1.0 + erf_fn(-d2 / math.sqrt(2.0)))


        delta = np.where(is_call_arr, ncdf_d1, ncdf_d1 - 1.0)
        gamma = npdf_d1 / (safe_spots * safe_sigmas * sqrt_t)
        vega  = safe_spots * npdf_d1 * sqrt_t / 100.0

        term1 = -(safe_spots * npdf_d1 * safe_sigmas) / (2.0 * sqrt_t)
        theta_call = (term1 - rates * safe_strikes * np.exp(-rates * times) * ncdf_d2) / 365.0
        theta_put  = (term1 + rates * safe_strikes * np.exp(-rates * times) * ncdf_neg_d2) / 365.0
        theta = np.where(is_call_arr, theta_call, theta_put)

        vanna = -npdf_d1 * d2 / safe_sigmas
        charm = -npdf_d1 * (rates / (safe_sigmas * sqrt_t) - d2 / (2.0 * np.maximum(times, 1e-8))) / 365.0

        # Sanitize NaN/Inf
        for arr in (delta, gamma, theta, vega, vanna, charm):
            np.nan_to_num(arr, copy=False, nan=0.0, posinf=0.0, neginf=0.0)

        return {
            "delta": delta, "gamma": gamma, "theta": theta,
            "vega": vega, "vanna": vanna, "charm": charm,
        }
    except Exception as exc:
        logger.warning("Vectorized batch failed (%s) — using scalar fallback", exc)

    # Scalar fallback
    results: dict[str, list[float]] = {
        k: [] for k in ("delta", "gamma", "theta", "vega", "vanna", "charm")
    }
    for i in range(n):
        otype = "C" if flags[i] == "c" else "P"
        g = compute_greeks(float(spots[i]), float(strikes[i]), float(times[i]),
                           float(rates[i]), float(sigmas[i]), otype)
        for k in results:
            results[k].append(g.get(k, 0.0))
    return {k: np.array(v, dtype=float) for k, v in results.items()}


# ---------------------------------------------------------------------------
# Dealer Exposure Functions
# ---------------------------------------------------------------------------

def dealer_gamma_exposure(
    open_interest: float, S: float, gamma: float, option_type: str = "C",
) -> float:
    """
    Dealer GEX for a single contract.

    Standard Market-Maker Sign Convention (SpotGamma / Quantwheel methodology):
      - Call Options: Retail buys calls → Dealers Short Calls → BUY spot on rally
        (dampens volatility). (+) Positive GEX = SUPPORT.
      - Put Options: Retail buys puts → Dealers Short Puts → SELL spot into drops
        (amplifies volatility). (-) Negative GEX = RESISTANCE.

    Returns: Dollar GEX per 1% move in underlying price.
    """
    dollar_gamma = gamma * S * S * 0.01 * open_interest
    is_call = option_type.upper() in ("C", "CALL")
    return dollar_gamma if is_call else -dollar_gamma


def dealer_vanna_exposure(
    open_interest: float, S: float, vanna: float, option_type: str = "C",
) -> float:
    """
    Dealer Vanna Exposure per 1pp move in Implied Volatility.

    When IV rises 1pp, dealers must buy/sell this many dollars of spot to re-hedge.
    Positive VEX → dealers are net buyers of spot when vol rises (vol squeeze fuel).
    Negative VEX → dealers are net sellers of spot when vol rises.

    Note: Option Vanna (∂Δ/∂σ) is identical for Calls and Puts.
    Dealer position is short client options → Dealer VEX = -OI × vanna × S × 0.01.
    """
    return -vanna * S * 0.01 * open_interest


def dealer_charm_exposure(
    open_interest: float, charm: float, option_type: str = "C",
) -> float:
    """
    Dealer Charm Exposure — daily delta bleed (delta decay per calendar day).

    Tells you how many dollars of spot the dealer will buy/sell tomorrow
    purely from time passing, even if price stays flat.
    Important for: weekend hedging drift, 0DTE expiry roll-off.

    Note: Option Charm (∂Δ/∂t) is identical for Calls and Puts.
    Dealer position is short client options → Dealer Charm = -OI × charm.
    """
    return -charm * open_interest
