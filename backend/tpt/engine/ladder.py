"""Ladder computation — pure function. No I/O.

Computes limit-order ladder levels (Tranche A 60%, Tranche B 40%, Stop, T1, T2)
for candidate symbols.
"""
from __future__ import annotations

from typing import Any

from tpt.config.strategy import LadderConfig
from tpt.engine.features import FeatureDict
from tpt.engine.labeler import Label
from tpt.engine.ws_memory import ws_memory

LadderDict = dict[str, Any]

def compute_ladder(
    product_id: str,
    features: FeatureDict,
    lbl: Label,
    composite_score: float = 50.0,
    config: LadderConfig | None = None,
    pinned: bool = False,
    trade_direction: str = "LONG",
    regime: str = "TRENDING_UP",
    base_position: float = 100.0,
    target_r: float | None = None,
) -> LadderDict | None:
    """Compute limit-order ladder levels for a candidate symbol.

    ``target_r`` is the calibrated distance to Target 1, in R multiples, from
    ``engine.exits``. When None the historical 2.0R default applies. Passing a
    measured value is how the ladder stops publishing a floor no trade can reach.

    Returns None if:
    - label is SKIP or CHASE (absolute block, even if pinned)
    - label is WATCH and symbol is not pinned
    """
    if "SKIP" in lbl or "CHASE" in lbl:
        return None

    if "WATCH" in lbl and not pinned:
        return None

    stop_pct = config.stop_pct / 100.0 if config else 0.03

    # Target-1 distance in R. 2.0 is the historical floor; a calibrated value
    # replaces it. Target 2 keeps its 2x relationship to T1, so only the scale of
    # the ladder changes, not its shape.
    t1_mult = float(target_r) if target_r and target_r > 0 else 2.0
    t2_mult = t1_mult * 2.0
    max_t2_mult = 8.0

    # Risk bounds, ATR-derived. The previous logic allowed a flat 5% clamp, which
    # on an asset whose whole favourable excursion is 1-3% made every R-multiple
    # target unreachable. Bounds that scale with the instrument's own volatility
    # mean R means roughly the same thing across 400 assets.
    atr_stop_mult = config.atr_stop_mult if config else 1.5
    min_risk_pct = config.min_stop_pct if config else 1.0
    max_risk_pct = config.max_stop_pct if config else 3.0

    last_price = float(features.get("last_price") or 0.0)
    vwap = float(features.get("vwap_24h") or last_price)
    
    atr_1h = float(features.get("atr_1h") or 0.0)
    atr_pct = (atr_1h / last_price * 100.0) if last_price > 0 else 2.0

    # The instrument's own risk unit, in percent. `atr_pct` is the 1h ATR as a
    # share of spot — how far this asset actually travels in an hour — which is
    # the only honest basis for how wide the stop should be. Bounded at both ends:
    # wide enough not to sit inside the noise, tight enough that R stays a
    # meaningful fraction of the move the asset can deliver.
    if atr_pct > 0:
        atr_risk_pct = max(min_risk_pct, min(max_risk_pct, atr_stop_mult * atr_pct))
    else:
        # No ATR to scale by. Fall back to the configured static stop rather than
        # the narrowest bound, which would place the stop inside the noise on the
        # one asset whose volatility we cannot see.
        atr_risk_pct = max(min_risk_pct, min(max_risk_pct, stop_pct * 100.0))
    risk_frac = atr_risk_pct / 100.0
    
    # Position Sizing
    # Fix 3: Constant-dollar risk sizing. Base position represents account equity.
    # Risk budget is scaled by confidence and regime, then divided by risk distance.
    risk_per_trade_pct = 0.03  # 3% maximum risk of base_position equity
    confidence = max(0.0, min(1.0, (composite_score - 50.0) / 50.0))
    regime_mult = {"TRENDING_UP": 1.0, "TRENDING_DOWN": 1.0, "RANGING": 0.85, "VOLATILE": 0.6}.get(regime, 1.0)
    
    risk_budget = (base_position * risk_per_trade_pct) * confidence * regime_mult
    total_size_usd = round(risk_budget / max(0.0001, risk_frac), 2)

    # Dynamic tranche scaling (scale into conviction strongly)
    if composite_score >= 80:
        tranche_a_size_pct = 70.0
        tranche_b_size_pct = 30.0
    elif composite_score >= 65:
        tranche_a_size_pct = 60.0
        tranche_b_size_pct = 40.0
    else:
        tranche_a_size_pct = 50.0
        tranche_b_size_pct = 50.0

    fib_236 = float(features.get("fib_236") or last_price)
    fib_382 = float(features.get("fib_382") or last_price)
    fib_500 = float(features.get("fib_500") or last_price)
    fib_618 = float(features.get("fib_618") or last_price)
    fib_786 = float(features.get("fib_786") or last_price)

    swing_shelf = features.get("swing_shelf_7d")
    swing_high = features.get("swing_high_7d")

    if trade_direction == "SHORT":
        # 1. SHORT Tranche A (60%): Midpoint of upper resistance (Fib 23.6-38.2) vs VWAP ceiling
        fib_mid = (fib_236 + fib_382) / 2.0
        vwap_pocket = vwap * 1.005
        tranche_a = max(fib_mid, vwap_pocket) if vwap_pocket > 0 else fib_mid
        tranche_a = max(tranche_a, last_price)

        # 2. SHORT Tranche B (40%): Higher resistance
        if swing_high is not None and float(swing_high) > 0:
            tranche_b = max(fib_236, float(swing_high))
        else:
            tranche_b = fib_236

        if tranche_b <= tranche_a:
            tranche_b = tranche_a * 1.04

        # 3. SHORT Stop Loss — structural where the book offers one, then bounded
        # into the instrument's own risk unit.
        stop_price = tranche_b * (1.0 + stop_pct)
        basis_stop = "Static Fallback (+3%)"

        l2_asks = features.get("l2_asks", [])

        if l2_asks:
            lb_stop = tranche_b * 1.01
            ub_stop = tranche_b * 1.04
            walls_b = [(float(x[0]), float(x[1])) for x in l2_asks if lb_stop <= float(x[0]) <= ub_stop]
            if walls_b:
                walls_b.sort(key=lambda x: x[1] * x[0], reverse=True)
                w_price, w_size = walls_b[0]
                if w_price * w_size >= 50_000:
                    stop_price = w_price * 1.0001
                    basis_stop = f"Tucked above ${w_price:,.4f} (+${(w_price * w_size)/1000:,.0f}k Wall)"

        # Bound the risk into [min, ATR-scaled max]. This replaces the old flat 5%
        # clamp: on an asset whose entire favourable excursion is 1-3%, a 5% stop
        # left R so wide that every R-multiple target was out of reach.
        risk_dist = stop_price - tranche_a
        min_dist = tranche_a * (min_risk_pct / 100.0)
        max_dist = tranche_a * risk_frac
        if risk_dist > max_dist:
            stop_price = tranche_a + max_dist
            basis_stop = f"Risk bounded to {atr_risk_pct:.2f}% (ATR-scaled, was wider)"
        elif risk_dist < min_dist:
            stop_price = tranche_a + min_dist
            basis_stop = f"Risk widened to {min_risk_pct:.2f}% floor"
        # Tranche B is a second sell above A, so it must sit *below* the stop.
        # Clamping the stop inward can otherwise leave the second entry outside it.
        if tranche_b >= stop_price:
            tranche_b = (tranche_a + stop_price) / 2.0

        risk = (stop_price - tranche_a) if stop_price > tranche_a else tranche_a * (min_risk_pct / 100.0)

        # 4. SHORT Target 1 — calibrated multiple when we have one, else the floor.
        target_1 = tranche_a - (t1_mult * risk)
        basis_t1 = (
            f"{t1_mult:.2f}R Target (calibrated from realised excursions)"
            if target_r
            else "Minimum 2.0R Target Floor"
        )

        # Target 2: keeps its 2x relationship to T1, capped at 8R.
        max_t2_price = tranche_a - (max_t2_mult * risk)
        target_2 = tranche_a - (t2_mult * risk)
        
        # L2 Target Interception for SHORT (looking for Buy Walls below entry)
        l2_bids = features.get("l2_bids", [])
        if l2_bids:
            walls_t = [(float(x[0]), float(x[1])) for x in l2_bids if target_1 <= float(x[0]) <= tranche_a * 0.99]
            if walls_t:
                walls_t.sort(key=lambda x: x[1] * x[0], reverse=True)
                wt_price, wt_size = walls_t[0]
                if wt_price * wt_size >= 50_000:
                    target_1 = wt_price * 1.0001
                    basis_t1 = f"Front-run ${wt_price:,.4f} (+${(wt_price * wt_size)/1000:,.0f}k Bid Wall)"

        # MACRO AI HEDGING (SHORT)
        options = ws_memory.get_macro_options(product_id.split("-")[0]) if "-" in product_id else None
        if options:
            gamma_walls = options.get("gamma_walls", [])
            calls = sorted([w["strike"] for w in gamma_walls if w["type"] == "RESISTANCE"])
            puts = sorted([w["strike"] for w in gamma_walls if w["type"] == "SUPPORT"])
            # Stop loss tucked safely behind a heavy Call Wall
            closest_call = next((w for w in calls if w > last_price), None)
            if closest_call and closest_call > tranche_b:
                stop_price = max(stop_price, closest_call * 1.005)
                basis_stop = "[GEX] Behind Macro Call Wall"
            # Target 1 tucked safely above a heavy Put Wall
            closest_put = next((w for w in reversed(puts) if w < last_price), None)
            if closest_put:
                target_1 = max(target_1, closest_put * 1.005)
                if abs(target_2 - target_1) < risk:
                    target_2 = max(target_2, closest_put * 1.002)
        if swing_shelf is not None and float(swing_shelf) < target_1:
            target_2 = max(float(swing_shelf), max_t2_price)

        if target_2 >= target_1:
            target_2 = target_1 - (2.0 * risk)

        rr_a_t1 = (tranche_a - target_1) / risk if risk > 0 else 0.0
        rr_a_t2 = (tranche_a - target_2) / risk if risk > 0 else 0.0
        basis_str_info = {"fib_mid": round(fib_mid, 8), "vwap_pocket": round(vwap_pocket, 8), "fib_786": round(fib_236, 8)}

    else:
        # LONG Logic
        fib_mid = (fib_500 + fib_618) / 2.0
        vwap_pocket = vwap * 0.995
        tranche_a = min(fib_mid, vwap_pocket) if vwap_pocket > 0 else fib_mid
        tranche_a = min(tranche_a, last_price)

        if swing_shelf is not None and float(swing_shelf) > 0:
            tranche_b = min(fib_786, float(swing_shelf))
        else:
            tranche_b = fib_786

        if tranche_b >= tranche_a:
            tranche_b = tranche_a * 0.96

        stop_price = tranche_b * (1.0 - stop_pct)
        basis_stop = "Static Fallback (-3%)"

        l2_bids = features.get("l2_bids", [])

        if l2_bids:
            lb_stop = tranche_b * 0.96
            ub_stop = tranche_b * 0.99
            walls_b = [(float(x[0]), float(x[1])) for x in l2_bids if lb_stop <= float(x[0]) <= ub_stop]
            if walls_b:
                walls_b.sort(key=lambda x: x[1] * x[0], reverse=True)
                w_price, w_size = walls_b[0]
                if w_price * w_size >= 50_000:
                    stop_price = w_price * 0.9999
                    basis_stop = f"Sunk below ${w_price:,.4f} (+${(w_price * w_size)/1000:,.0f}k Wall)"

        # Bound the risk into [min, ATR-scaled max] — see the SHORT branch.
        risk_dist = tranche_a - stop_price
        min_dist = tranche_a * (min_risk_pct / 100.0)
        max_dist = tranche_a * risk_frac
        if risk_dist > max_dist:
            stop_price = tranche_a - max_dist
            basis_stop = f"Risk bounded to {atr_risk_pct:.2f}% (ATR-scaled, was wider)"
        elif risk_dist < min_dist:
            stop_price = tranche_a - min_dist
            basis_stop = f"Risk widened to {min_risk_pct:.2f}% floor"
        # Tranche B is a second buy below A, so it must sit *above* the stop.
        if tranche_b <= stop_price:
            tranche_b = (tranche_a + stop_price) / 2.0

        risk = (tranche_a - stop_price) if tranche_a > stop_price else tranche_a * (min_risk_pct / 100.0)

        # LONG Target 1 — calibrated multiple when available, else the floor.
        target_1 = tranche_a + (t1_mult * risk)
        basis_t1 = (
            f"{t1_mult:.2f}R Target (calibrated from realised excursions)"
            if target_r
            else "Minimum 2.0R Target Extension"
        )

        max_t2_price = tranche_a + (max_t2_mult * risk)
        target_2 = tranche_a + (t2_mult * risk)
        
        # L2 Target Interception for LONG (looking for Sell Walls above entry)
        l2_asks = features.get("l2_asks", [])
        if l2_asks:
            walls_t = [(float(x[0]), float(x[1])) for x in l2_asks if tranche_a * 1.01 <= float(x[0]) <= target_1]
            if walls_t:
                walls_t.sort(key=lambda x: x[1] * x[0], reverse=True)
                wt_price, wt_size = walls_t[0]
                if wt_price * wt_size >= 50_000:
                    target_1 = wt_price * 0.9999
                    basis_t1 = f"Front-run ${wt_price:,.4f} (+${(wt_price * wt_size)/1000:,.0f}k Ask Wall)"

        # MACRO AI HEDGING (LONG)
        options = ws_memory.get_macro_options(product_id.split("-")[0]) if "-" in product_id else None
        if options:
            gamma_walls = options.get("gamma_walls", [])
            calls = sorted([w["strike"] for w in gamma_walls if w["type"] == "RESISTANCE"])
            puts = sorted([w["strike"] for w in gamma_walls if w["type"] == "SUPPORT"])
            # Stop loss safely underneath a massive Put Wall
            closest_put = next((w for w in reversed(puts) if w < last_price), None)
            if closest_put and closest_put < tranche_b:
                stop_price = min(stop_price, closest_put * 0.995)
                basis_stop = "[GEX] Below Macro Put Wall"
            # Target 1 capped underneath a major Dealer Call Wall to secure fills
            closest_call = next((w for w in calls if w > last_price), None)
            if closest_call:
                target_1 = min(target_1, closest_call * 0.995)
                if abs(target_2 - target_1) < risk:
                    target_2 = min(target_2, closest_call * 0.998)
        if swing_high is not None and float(swing_high) > target_1:
            target_2 = min(float(swing_high), max_t2_price)

        if target_2 <= target_1:
            target_2 = target_1 + (2.0 * risk)

        rr_a_t1 = (target_1 - tranche_a) / risk if risk > 0 else 0.0
        rr_a_t2 = (target_2 - tranche_a) / risk if risk > 0 else 0.0
        basis_str_info = {"fib_mid": round(fib_mid, 8), "vwap_pocket": round(vwap_pocket, 8), "fib_786": round(fib_786, 8)}

    # R/R structural filter. The floor exists so the ladder never publishes a poor
    # payoff — but a fixed 1.85R floor is also what made every target unreachable
    # once the realised excursion proved to be under 1R. When a target has been
    # calibrated, the measurement supersedes the constant.
    min_rr = 1.85
    if target_r and target_r > 0:
        min_rr = min(min_rr, float(target_r))
    if rr_a_t1 < min_rr and not pinned:
        return None

    basis_dict = {
        **basis_str_info,
        "swing_shelf": round(float(swing_shelf), 6) if swing_shelf is not None else None,
        "stop_logic": basis_stop,
        "tp1_logic": basis_t1,
    }

    res_dict = {
        "tranche_a_price": round(tranche_a, 6),
        "tranche_b_price": round(tranche_b, 6),
        "stop_price": round(stop_price, 6),
        "target_1_price": round(target_1, 6),
        "target_2_price": round(target_2, 6),
        "tranche_a_size_pct": tranche_a_size_pct,
        "tranche_b_size_pct": tranche_b_size_pct,
        "total_size_usd": total_size_usd,
        "rr_a_t1": round(rr_a_t1, 2),
        "rr_a_t2": round(rr_a_t2, 2),
        # Carried on the ladder itself so `sanitize_ladder_dict` — which runs over
        # persisted and historical ladders too — honours the calibrated multiple
        # instead of forcing T1 back out to its hardcoded 2.0R.
        "target_r": round(t1_mult, 3),
        "basis": basis_dict,
        "trade_direction": trade_direction,
    }
    return sanitize_ladder_dict(res_dict)


def format_ladder_text(
    product_id: str,
    score_val: float,
    lbl: str,
    ladder: LadderDict,
) -> str:
    """Format limit-ladder levels into the PRD §8 copyable text template."""
    def _fmt(v: float | None) -> str:
        if v is None:
            return "-"
        if v < 0.0001:
            return f"${v:.6f}"
        elif v < 1.0:
            return f"${v:.5f}"
        elif v < 10.0:
            return f"${v:.3f}"
        else:
            return f"${v:.2f}"

    tr_a = _fmt(ladder.get("tranche_a_price"))
    tr_b = _fmt(ladder.get("tranche_b_price"))
    stop_p = _fmt(ladder.get("stop_price"))
    t1 = _fmt(ladder.get("target_1_price"))
    t2 = _fmt(ladder.get("target_2_price"))

    rr1 = ladder.get("rr_a_t1", 0.0)
    rr2 = ladder.get("rr_a_t2", 0.0)
    dir_str = ladder.get("trade_direction", "LONG")

    # The tranche split is dynamic (70/30 above a score of 80, 60/40 above 65),
    # so labelling every ladder "60%/40%" told the operator something the plan
    # did not say. Same for the fixed "(4.0R Ext)" on a target that is often
    # well beyond 4R by the time the risk clamp and wall front-running land.
    a_pct = ladder.get("tranche_a_size_pct", 60)
    b_pct = ladder.get("tranche_b_size_pct", 40)
    a_pct_s = f"{a_pct:.0f}" if isinstance(a_pct, (int, float)) else "60"
    b_pct_s = f"{b_pct:.0f}" if isinstance(b_pct, (int, float)) else "40"

    basis = ladder.get("basis", {})
    basis_str = f"VWAP pocket {_fmt(basis.get('vwap_pocket'))} + Macro {_fmt(basis.get('fib_786'))}"
    stop_lgc = basis.get('stop_logic', '')
    tp1_lgc = basis.get('tp1_logic', '')

    lines = [
        f"[{product_id}] - {lbl} [{dir_str}] (Score: {score_val:.0f})",
        "-" * 40,
        f"Tranche A ({a_pct_s}%): {tr_a:<10} | R/R T1: {rr1:.2f}R",
        f"Tranche B ({b_pct_s}%): {tr_b:<10} | R/R T2: {rr2:.2f}R",
        f"Stop Loss:       {stop_p:<10} {stop_lgc}",
        "-" * 40,
        f"Target 1:        {t1:<10} {tp1_lgc}",
        f"Target 2:        {t2:<10} ({rr2:.2f}R Ext)",
        f"Basis: {basis_str}",
    ]
    return "\n".join(lines)


def sanitize_ladder_dict(lad_dict: dict[str, Any] | None) -> dict[str, Any] | None:
    """Bring any ladder dict (active or historical) onto institutional footing.

    T1 sits at ``target_r`` multiples of risk, T2 at twice that, both bounded by
    the 1R-8R envelope the ladder works in. ``target_r`` is read off the ladder
    when present so a calibrated target survives this function — it previously
    hardcoded 2.0 and so silently overrode any calibration back to an unreachable
    distance. Ladders written before the field existed keep the 2.0 default.
    """
    if not lad_dict or not lad_dict.get("tranche_a_price"):
        return lad_dict

    try:
        tranche_a = float(lad_dict["tranche_a_price"])
        stop = float(lad_dict.get("stop_price") or 0.0)
        t1 = float(lad_dict.get("target_1_price") or 0.0)
        t2 = float(lad_dict.get("target_2_price") or 0.0)

        if tranche_a <= 0 or stop <= 0:
            return lad_dict

        is_short = stop > tranche_a

        # The calibrated multiple, clamped to the envelope the ladder works in.
        try:
            target_r = float(lad_dict.get("target_r") or 2.0)
        except (TypeError, ValueError):
            target_r = 2.0
        target_r = max(0.1, min(8.0, target_r))

        # Loose backstop only — compute_ladder already bounds risk to the
        # ATR-derived band. This catches hand-written or historical rows.
        max_risk_frac = 0.055

        if is_short:
            risk = stop - tranche_a
            if risk > tranche_a * max_risk_frac:
                risk = tranche_a * max_risk_frac
                stop = tranche_a + risk
                lad_dict["stop_price"] = round(stop, 8)

            min_t1 = tranche_a - (target_r * risk)
            if t1 > min_t1 or t1 <= 0:
                lad_dict["target_1_price"] = round(min_t1, 8)
                t1 = min_t1

            min_t2 = tranche_a - (target_r * 2.0 * risk)
            if t2 > t1 or t2 <= 0:
                lad_dict["target_2_price"] = round(min_t2, 8)
                t2 = min_t2

            lad_dict["rr_a_t1"] = round(abs(tranche_a - t1) / risk, 2) if risk > 0 else target_r
            lad_dict["rr_a_t2"] = (
                round(abs(tranche_a - t2) / risk, 2) if risk > 0 else target_r * 2.0
            )
        else:
            risk = tranche_a - stop
            if risk > tranche_a * max_risk_frac:
                risk = tranche_a * max_risk_frac
                stop = tranche_a - risk
                lad_dict["stop_price"] = round(stop, 8)

            min_t1 = tranche_a + (target_r * risk)
            if t1 < min_t1 or t1 <= 0:
                lad_dict["target_1_price"] = round(min_t1, 8)
                t1 = min_t1

            min_t2 = tranche_a + (target_r * 2.0 * risk)
            if t2 < t1 or t2 <= 0:
                lad_dict["target_2_price"] = round(min_t2, 8)
                t2 = min_t2

            lad_dict["rr_a_t1"] = round(abs(t1 - tranche_a) / risk, 2) if risk > 0 else target_r
            lad_dict["rr_a_t2"] = (
                round(abs(t2 - tranche_a) / risk, 2) if risk > 0 else target_r * 2.0
            )

    except Exception:
        pass

    return lad_dict
