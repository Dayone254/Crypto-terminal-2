"""
Institutional Gamma Analytics
=============================
Pure-function analytics layered on top of the GEX engine's per-strike
accumulators. Everything here derives from the real options board — no
synthetic numbers. Consumers: options_flow.py (payload fields) and the
ws_memory regime loop (flip tracking).

Conventions
-----------
- GEX values are dealer dollar-gamma per 1% spot move (SpotGamma sign
  convention: positive = dealer buys dips / sells rallies = stability).
- IVs are decimal (0.55 = 55%). Percent-suffixed fields (*_pct) are ×100.
- OI is in coin contracts unless the field name says _usd.
"""
from __future__ import annotations

import logging
import math
import time
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. MAX PAIN — strike minimizing total intrinsic payout at expiry
# ---------------------------------------------------------------------------

def compute_max_pain(
    strike_call_oi: dict[float, float],
    strike_put_oi: dict[float, float],
    spot: float,
) -> float | None:
    """Settlement price that inflicts the least value on option holders.

    pain(K) = Σ call_oi_i × max(K − K_i, 0) + Σ put_oi_i × max(K_i − K, 0).
    The classic expiry-magnet level. Returns None with no OI.
    """
    if not strike_call_oi and not strike_put_oi:
        return None
    candidates = sorted(set(strike_call_oi) | set(strike_put_oi))
    best_k: float | None = None
    best_pain = float("inf")
    for k in candidates:
        pain = 0.0
        for ki, oi in strike_call_oi.items():
            if k > ki:
                pain += oi * (k - ki)
        for ki, oi in strike_put_oi.items():
            if ki > k:
                pain += oi * (ki - k)
        # Tie-break toward the strike nearer spot (max pain is a magnet, not a
        # coin flip between two equidistant candidates).
        if pain < best_pain - 1e-9 or (
            abs(pain - best_pain) <= 1e-9
            and best_k is not None
            and abs(k - spot) < abs(best_k - spot)
        ):
            best_pain = pain
            best_k = k
    return best_k


# ---------------------------------------------------------------------------
# 2. SKEW — 25-delta risk reversal & butterfly (standardized skew metrics)
# ---------------------------------------------------------------------------

def compute_skew_metrics(
    board: list[dict],
    spot: float,
) -> dict[str, Any] | None:
    """RR25 (call−put IV) and Fly25 (wings − 2×ATM) for the most populated
    nearby expiry. Standard desk convention: RR25 < 0 = puts bid (crash hedge
    demand). Returns None when the board cannot support the measurement."""
    if not board or spot <= 0:
        return None

    from tpt.engine.options_flow import parse_expiry  # lazy: avoid import cycle

    # Group by expiry, keep the bucket with the most two-sided OI.
    buckets: dict[str, dict[str, list[float]]] = {}
    for opt in board:
        try:
            iv = float(opt.get("implied_volatility", 0) or 0)
            k = float(opt.get("strike", 0) or 0)
        except (TypeError, ValueError):
            continue
        if iv <= 0.01 or iv > 5.0 or k <= 0:
            continue
        exp = str(opt.get("expiry_str", ""))
        b = buckets.setdefault(exp, {"calls": [], "puts": []})
        otype = str(opt.get("type", "")).upper()
        (b["calls"] if otype in ("C", "CALL") else b["puts"]).append((k, iv))

    if not buckets:
        return None

    def _twosided_score(b: dict) -> float:
        return float(min(len(b["calls"]), len(b["puts"])))

    # Prefer ~7-30 DTE buckets (stable skew), fall back to most two-sided.
    ranked = sorted(
        buckets.items(),
        key=lambda kv: (
            _twosided_score(kv[1]) >= 2,
            8.0 >= (parse_expiry(kv[0]) * 365.25) >= 1.0,
            _twosided_score(kv[1]),
        ),
        reverse=True,
    )
    from tpt.engine.greeks_engine import compute_greeks

    def _iv_at_delta(entries: list[tuple[float, float]], target_abs_delta: float,
                     is_call: bool, T: float) -> tuple[float, float] | None:
        best: tuple[float, float] | None = None  # (iv, |Δ − target|)
        for k, iv in entries:
            g = compute_greeks(spot, k, T, 0.05, iv, "C" if is_call else "P")
            if abs(g["delta"]) < 1e-6:
                continue
            err = abs(abs(g["delta"]) - target_abs_delta)
            if best is None or err < best[1]:
                best = (iv, err)
        if best is None or best[1] > 0.12:  # no contract near 25Δ → unreliable
            return None
        return best

    # Try ranked expiry buckets in order: a bucket whose wings miss the 25Δ
    # gate shouldn't kill the measurement if a neighbouring expiry carries it.
    for exp, bucket in ranked:
        if _twosided_score(bucket) < 2:
            continue
        T = parse_expiry(exp)
        if T <= 0:
            continue

        call25 = _iv_at_delta(bucket["calls"], 0.25, True, T)
        put25 = _iv_at_delta(bucket["puts"], 0.25, False, T)

        # ATM IV: contract(s) nearest spot in this expiry.
        all_ks = [k for k, _ in bucket["calls"] + bucket["puts"]]
        if not all_ks:
            continue
        atm_k = min(all_ks, key=lambda k: abs(k - spot))
        atm_ivs = [iv for k, iv in bucket["calls"] + bucket["puts"] if k == atm_k]
        atm_iv = sum(atm_ivs) / len(atm_ivs) if atm_ivs else None

        if call25 is None or put25 is None or atm_iv is None:
            continue

        rr25 = (call25[0] - put25[0]) * 100.0
        fly25 = (call25[0] + put25[0] - 2.0 * atm_iv) * 100.0
        return {
            "rr25_pct": round(rr25, 2),
            "fly25_pct": round(fly25, 2),
            "ref_expiry": exp,
        }
    return None


# ---------------------------------------------------------------------------
# 3. EXPIRY CLUSTERS — where the notional actually sits
# ---------------------------------------------------------------------------

def compute_expiry_clusters(
    board: list[dict],
    max_clusters: int = 5,
) -> list[dict[str, Any]]:
    """Notional OI grouped by expiry, largest first, with 0DTE share."""
    if not board:
        return []
    from tpt.engine.options_flow import parse_expiry  # lazy: avoid cycle

    agg: dict[str, dict[str, float]] = {}
    for opt in board:
        try:
            # Real boards carry USD notional; fall back to raw contracts so
            # minimal/synthetic inputs still rank (ranking is scale-invariant).
            oi_usd = float(opt.get("open_interest_usd", 0) or 0)
            if oi_usd == 0:
                oi_usd = float(opt.get("open_interest", 0) or 0)
        except (TypeError, ValueError):
            continue
        exp = str(opt.get("expiry_str", ""))
        otype = str(opt.get("type", "")).upper()
        a = agg.setdefault(exp, {"total": 0.0, "call": 0.0, "put": 0.0})
        a["total"] += oi_usd
        if otype in ("C", "CALL"):
            a["call"] += oi_usd
        else:
            a["put"] += oi_usd

    grand = sum(a["total"] for a in agg.values())
    if grand <= 0:
        return []

    clusters = []
    zero_dte = 0.0
    for exp, a in agg.items():
        dte = parse_expiry(exp) * 365.25
        if dte <= 1.0:
            zero_dte += a["total"]
        clusters.append({
            "expiry": exp,
            "dte": round(dte, 1),
            "total_oi_usd": round(a["total"], 0),
            "call_oi_usd": round(a["call"], 0),
            "put_oi_usd": round(a["put"], 0),
            "share_pct": round(a["total"] / grand * 100.0, 1),
        })
    clusters.sort(key=lambda c: c["total_oi_usd"], reverse=True)
    out = clusters[:max_clusters]
    out.append({
        "expiry": "_0DTE_SHARE",
        "dte": 0.0,
        "total_oi_usd": round(zero_dte, 0),
        "call_oi_usd": 0.0,
        "put_oi_usd": 0.0,
        "share_pct": round(zero_dte / grand * 100.0, 1),
    })
    return out


# ---------------------------------------------------------------------------
# 4. DEALER HEDGING PROFILE — who must buy/sell what, near spot
# ---------------------------------------------------------------------------

def compute_hedging_profile(
    strike_net_gex: dict[float, float],
    spot: float,
    band_pct: float = 5.0,
    strike_call_gex: dict[float, float] | None = None,
    strike_put_gex: dict[float, float] | None = None,
) -> dict[str, Any]:
    """Net dealer hedging pressure around spot.

    Support: strikes at/below spot where dealers must buy dips — positive net
    GEX (dealer long gamma there).

    Resistance: strikes above spot where dealer hedging caps upside. Two
    mechanisms count:
    - Positive call GEX (the call wall): dealers are long gamma there and
      sell into rallies as spot grinds up toward the strike — a pin that
      acts as resistance. On the long-gamma boards that dominate crypto,
      this is the DOMINANT upside force; using net GEX only misses it
      because net = call + put gamma and the put leg's short gamma cancels
      the call leg at the wall strike.
    - Negative net GEX (dealer short gamma there): hedging accelerates the
      move away from the strike, suppressing rallies — kept as a secondary
      contributor, never double-counted (a strike contributes once, at its
      larger mechanism).

    ``strike_call_gex`` / ``strike_put_gex`` are optional; without them the
    profile falls back to the historical net-only reading (resistance =
    negative net GEX above spot only).
    """
    empty = {
        "bias": "NEUTRAL", "downside_support_gex_m": 0.0,
        "upside_resistance_gex_m": 0.0, "top_supportive": [],
        "top_suppressive": [],
    }
    if not strike_net_gex or spot <= 0:
        return empty

    band = spot * band_pct / 100.0
    support = [(k, g) for k, g in strike_net_gex.items()
               if spot - band <= k <= spot and g > 0]

    resist_by_strike: dict[float, float] = {}
    if strike_call_gex is None and strike_put_gex is None:
        # Legacy callers / minimal inputs: net-only reading.
        for k, g in strike_net_gex.items():
            if spot < k <= spot + band and g < 0:
                resist_by_strike[k] = abs(g)
    else:
        call_gex = strike_call_gex or {}
        put_gex = strike_put_gex or {}
        for k in strike_net_gex:
            if not (spot < k <= spot + band):
                continue
            net = strike_net_gex[k]
            call_pin = max(call_gex.get(k, 0.0), 0.0)   # call wall: pin/ceiling
            put_accel = max(-put_gex.get(k, 0.0), 0.0)  # short put gamma: chase fuel
            pressure = max(call_pin, put_accel, abs(net) if net < 0 else 0.0)
            if pressure > 0:
                resist_by_strike[k] = pressure

    sup_total = sum(g for _, g in support) / 1e6
    res_total = sum(resist_by_strike.values()) / 1e6

    top_sup = sorted(support, key=lambda x: x[1], reverse=True)[:3]
    top_res = sorted(resist_by_strike.items(), key=lambda x: x[1], reverse=True)[:3]

    if sup_total + res_total < 0.5:
        bias = "NEUTRAL"
    elif sup_total > res_total * 1.3:
        bias = "SUPPORTIVE"
    elif res_total > sup_total * 1.3:
        bias = "SUPPRESSIVE"
    else:
        bias = "MIXED"

    return {
        "bias": bias,
        "downside_support_gex_m": round(sup_total, 2),
        "upside_resistance_gex_m": round(res_total, 2),
        "top_supportive": [{"strike": k, "gex_m": round(g / 1e6, 2)} for k, g in top_sup],
        "top_suppressive": [{"strike": k, "gex_m": round(g / 1e6, 2)} for k, g in top_res],
    }


# ---------------------------------------------------------------------------
# 5. PIN MAP — gamma-weighted expiry magnets
# ---------------------------------------------------------------------------

def compute_pin_map(
    strike_net_gex: dict[float, float],
    spot: float,
    max_pins: int = 3,
    max_dist_pct: float = 10.0,
) -> list[dict[str, Any]]:
    """Attraction strength of positive-gamma strikes: γ ∝ 1/dist². Only
    positive-gamma strikes pin (dealers defend them); negative-gamma strikes
    repel and are excluded."""
    if not strike_net_gex or spot <= 0:
        return []
    pins = []
    for k, g in strike_net_gex.items():
        if g <= 0:
            continue
        dist_pct = abs(k - spot) / spot * 100.0
        if dist_pct > max_dist_pct:
            continue
        weight = g / (dist_pct + 0.25) ** 2
        pins.append({"strike": k, "gex_m": round(g / 1e6, 2),
                     "dist_pct": round(dist_pct, 2), "weight": weight})
    pins.sort(key=lambda p: p["weight"], reverse=True)
    top = pins[:max_pins]
    peak = top[0]["weight"] if top else 1.0
    for p in top:
        p["strength"] = round(p.pop("weight") / peak * 100.0, 0)
    return top


# ---------------------------------------------------------------------------
# 6. CONFIDENCE GRADE — how much the payload deserves your trust
# ---------------------------------------------------------------------------

def compute_confidence(
    board: list[dict],
    venue_metrics: dict[str, Any],
    spot: float,
    vol_surface_fitted: bool,
) -> dict[str, Any]:
    """Deterministic 0-100 grade of data quality with component reasons."""
    reasons: list[str] = []
    score = 0.0

    venues = venue_metrics.get("active_venues", []) or []
    v_score = min(len(venues), 4) / 4.0 * 25.0
    score += v_score
    reasons.append(f"{len(venues)} venue(s) live" if venues else "no venues live")

    n = len(board)
    c_score = min(n, 200) / 200.0 * 25.0
    score += c_score
    reasons.append(f"{n} contracts" if n else "empty board")

    oi_usd = float(venue_metrics.get("total_open_interest_usd", 0) or 0)
    o_score = min(oi_usd / 1e8, 1.0) * 20.0
    score += o_score
    reasons.append(f"${oi_usd / 1e6:,.0f}M OI" if oi_usd > 0 else "no OI notional")

    if vol_surface_fitted:
        score += 15.0
        reasons.append("SABR surface fitted")
    else:
        reasons.append("raw venue IVs")

    if spot > 0:
        score += 10.0
    else:
        reasons.append("no spot anchor")
    score += 5.0  # freshness: payload is computed, not cached page-side

    score = round(score)
    grade = ("A" if score >= 80 else "B" if score >= 65 else
             "C" if score >= 50 else "D" if score >= 35 else "F")
    return {"score": score, "grade": grade, "reasons": reasons}


# ---------------------------------------------------------------------------
# 7. ORCHESTRATOR — one call from options_flow
# ---------------------------------------------------------------------------

def compute_institutional_analytics(
    board: list[dict],
    spot_price: float,
    strike_net_gex: dict[float, float],
    strike_call_gex: dict[float, float],
    strike_put_gex: dict[float, float],
    strike_call_oi: dict[float, float],
    strike_put_oi: dict[float, float],
    venue_metrics: dict[str, Any],
    vol_surface_fitted: bool,
) -> dict[str, Any]:
    return {
        "max_pain": compute_max_pain(strike_call_oi, strike_put_oi, spot_price),
        "skew": compute_skew_metrics(board, spot_price),
        "expiry_clusters": compute_expiry_clusters(board),
        "hedging_profile": compute_hedging_profile(
            strike_net_gex, spot_price,
            strike_call_gex=strike_call_gex,
            strike_put_gex=strike_put_gex,
        ),
        "pin_map": compute_pin_map(strike_net_gex, spot_price),
        "confidence": compute_confidence(board, venue_metrics, spot_price,
                                         vol_surface_fitted),
    }


# ---------------------------------------------------------------------------
# 8. REGIME TRACKER — flip confirmation, transition memory, alerting hook
# ---------------------------------------------------------------------------

class GammaRegimeTracker:
    """Confirms regime flips only after they HOLD for ``min_hold_seconds``.

    Whipsaw protection: LONG↔SHORT gamma flaps near the flip line are noise;
    a flip that persists across the hold window is a regime event worth
    alerting on. Keeps the last ``history_len`` committed transitions per
    underlying for the UI's regime memory panel.
    """

    def __init__(self, min_hold_seconds: float = 600.0, history_len: int = 20):
        self.min_hold_seconds = min_hold_seconds
        self.history_len = history_len
        self._state: dict[str, dict[str, Any]] = {}
        self._hydrated = False

    def observe(
        self, underlying: str, regime: str, spot: float, now: float | None = None,
    ) -> dict[str, Any] | None:
        """Feed one observation. Returns the committed flip (dict) or None."""
        now = time.time() if now is None else now
        self._hydrate()
        st = self._state.setdefault(underlying, {
            "regime": regime, "since": now,
            "candidate": regime, "candidate_since": now, "transitions": [],
        })

        if regime != st["candidate"]:
            st["candidate"] = regime
            st["candidate_since"] = now
            return None

        if regime == st["regime"]:
            st["candidate_since"] = now
            return None

        if now - st["candidate_since"] < self.min_hold_seconds:
            return None

               # Flip confirmed.
        flip = {
            "ts": now, "from": st["regime"], "to": regime, "spot": spot,
        }
        st["regime"] = regime
        st["since"] = now
        st["transitions"].append(flip)
        if len(st["transitions"]) > self.history_len:
            st["transitions"] = st["transitions"][-self.history_len:]
        self._persist_open()
        return flip

    def transitions(self, underlying: str) -> list[dict[str, Any]]:
        return list(self._state.get(underlying, {}).get("transitions", []))

    def state_age(self, underlying: str, now: float | None = None) -> float | None:
        now = time.time() if now is None else now
        st = self._state.get(underlying)
        return None if st is None else now - st["since"]

    # ── Persistence ───────────────────────────────────────────────────────────
    # Flip history and in-progress hold windows survive backend restarts —
    # otherwise every deploy wipes the regime memory the UI panel and the
    # hold-based confirmation depend on. Writes happen only on confirmed
    # flips (rare), so contention with the main DB is a non-issue.

    @staticmethod
    def _persist_path() -> str:
        """Small dedicated store: keeps the 5.3GB main DB out of the hot path."""
        try:
            from tpt.data.database import DB_PATH
            return str(DB_PATH) + ".regime"
        except Exception:
            return "regime_state.db"

    def _persist_open(self) -> None:
        """Best-effort synchronous write of current state. Never raises."""
        try:
            import json as _json
            import os as _os
            import sqlite3 as _sqlite3

            path = self._persist_path()
            _os.makedirs(_os.path.dirname(path) or ".", exist_ok=True)
            conn = _sqlite3.connect(path)
            try:
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS regime_state (
                        underlying TEXT PRIMARY KEY,
                        state_json TEXT NOT NULL,
                        updated_at REAL NOT NULL
                    )"""
                )
                conn.execute("DELETE FROM regime_state")
                conn.executemany(
                    "INSERT INTO regime_state (underlying, state_json, updated_at) VALUES (?, ?, ?)",
                    [
                        (u, _json.dumps(st), time.time())
                        for u, st in self._state.items()
                    ],
                )
                conn.commit()
            finally:
                conn.close()
        except Exception:  # persistence is best-effort; never break tracking
            logger.debug("regime tracker persist failed", exc_info=True)

    def _hydrate(self) -> None:
        """Load persisted state once, on first use after process start."""
        if self._hydrated:
            return
        self._hydrated = True
        try:
            import json as _json
            import os as _os
            import sqlite3 as _sqlite3

            path = self._persist_path()
            if not _os.path.exists(path):
                return
            conn = _sqlite3.connect(path)
            try:
                rows = conn.execute("SELECT underlying, state_json FROM regime_state").fetchall()
            finally:
                conn.close()
            for u, blob in rows:
                try:
                    self._state[u] = _json.loads(blob)
                except Exception:
                    continue
            if rows:
                logger.info("Regime tracker restored %d underlying(s) from disk.", len(rows))
        except Exception:
            logger.debug("regime tracker hydrate failed", exc_info=True)


_TRACKER = GammaRegimeTracker()


def get_regime_tracker() -> GammaRegimeTracker:
    return _TRACKER
