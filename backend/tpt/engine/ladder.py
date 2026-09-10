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
) -> LadderDict | None:
    """Compute limit-order ladder levels for a candidate symbol.
    
    Returns None if:
    - label is SKIP or CHASE (absolute block, even if pinned)
    - label is WATCH and symbol is not pinned
    """
    if "SKIP" in lbl or "CHASE" in lbl:
        return None

    if "WATCH" in lbl and not pinned:
        return None

    stop_pct = config.stop_pct / 100.0 if config else 0.03
    ext_pct = config.target2_extension_pct / 100.0 if config else 0.05

    last_price = float(features.get("last_price") or 0.0)
    day_high = float(features.get("day_high") or last_price)
    day_low = float(features.get("day_low") or last_price)
    vwap = float(features.get("vwap_24h") or last_price)
    
    atr_1h = float(features.get("atr_1h") or 0.0)
    atr_pct = (atr_1h / last_price * 100.0) if last_price > 0 else 2.0
    
    # Position Sizing
    vol_scale = max(0.3, min(1.0, 1.0 - (atr_pct / 10.0)))
    confidence = max(0.0, min(1.0, (composite_score - 50.0) / 50.0))
    regime_mult = {"TRENDING_UP": 1.0, "TRENDING_DOWN": 1.0, "RANGING": 0.85, "VOLATILE": 0.6}.get(regime, 1.0)
    total_size_usd = round(base_position * vol_scale * confidence * regime_mult, 2)

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

        # 3. SHORT Stop Loss
        # 3. SHORT Stop Loss (Tight clamp to max 3.0% risk of tranche_a)
        stop_price = tranche_b * (1.0 + stop_pct)
        basis_stop = "Static Fallback (+3%)"

        l2_asks = features.get("l2_asks", [])
        atr_14d = features.get("atr_14d")

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
            elif atr_14d and atr_14d > 0:
                stop_price = tranche_b + (atr_14d * 2.0)
                basis_stop = f"ATR Fallback (2x = ${atr_14d*2:,.4f})"

        # Clamp risk to max 5.5% of tranche_a for volatile crypto asset volatility
        if (stop_price - tranche_a) > tranche_a * 0.055:
            stop_price = tranche_a * 1.05
            tranche_b = (tranche_a + stop_price) / 2.0
            basis_stop = "Risk Clamp (+5%)"

        risk = stop_price - tranche_a if stop_price > tranche_a else tranche_a * 0.03

        # 4. SHORT Target 1 (Strictly 1:2.0 R/R Floor) & Target 2 (Strictly 1:4.0 R/R to 1:8.0 R/R)
        min_t1 = tranche_a - (2.0 * risk)
        target_1 = min_t1
        basis_t1 = "Minimum 2.0R Target Floor"

        # Target 2: Extend to 4.0R to 8.0R
        max_t2_price = tranche_a - (8.0 * risk)
        target_2 = tranche_a - (4.0 * risk)
        
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
        atr_14d = features.get("atr_14d")
        
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
            elif atr_14d and atr_14d > 0:
                stop_price = tranche_b - (atr_14d * 2.0)
                basis_stop = f"ATR Fallback (2x = ${atr_14d*2:,.4f})"

        # Clamp risk to max 5.5% of tranche_a for volatile crypto asset volatility
        if (tranche_a - stop_price) > tranche_a * 0.055:
            stop_price = tranche_a * 0.95
            tranche_b = (tranche_a + stop_price) / 2.0
            basis_stop = "Risk Clamp (-5%)"

        risk = (tranche_a - stop_price) if tranche_a > stop_price else tranche_a * 0.03

        # LONG Target 1 (Strictly 1:2.0 R/R Floor) & Target 2 (Strictly 1:4.0 R/R to 1:8.0 R/R)
        target_1 = tranche_a + (2.0 * risk)
        basis_t1 = "Minimum 2.0R Target Extension"
        
        max_t2_price = tranche_a + (8.0 * risk)
        target_2 = tranche_a + (4.0 * risk)
        
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

    # R/R Structural Filter Constraint (Minimum 1.85R required to allow for L2 wall front-running)
    if rr_a_t1 < 1.85 and not pinned:
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

    basis = ladder.get("basis", {})
    basis_str = f"VWAP pocket {_fmt(basis.get('vwap_pocket'))} + Macro {_fmt(basis.get('fib_786'))}"
    stop_lgc = basis.get('stop_logic', '')
    tp1_lgc = basis.get('tp1_logic', '')

    lines = [
        f"[{product_id}] - {lbl} [{dir_str}] (Score: {score_val:.0f})",
        "-" * 40,
        f"Tranche A (60%): {tr_a:<10} | R/R T1: {rr1:.2f}R",
        f"Tranche B (40%): {tr_b:<10} | R/R T2: {rr2:.2f}R",
        f"Stop Loss:       {stop_p:<10} {stop_lgc}",
        "-" * 40,
        f"Target 1:        {t1:<10} {tp1_lgc}",
        f"Target 2:        {t2:<10} (4.0R Ext)",
        f"Basis: {basis_str}",
    ]
    return "\n".join(lines)


def sanitize_ladder_dict(lad_dict: dict[str, Any] | None) -> dict[str, Any] | None:
    """Sanitize any ladder dictionary (active or historical) to guarantee 1:2.0R to 1:8.0R institutional constraints."""
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

        if is_short:
            risk = stop - tranche_a
            # Clamp loose stop loss to max 5.5% of tranche_a (matches compute_ladder threshold)
            if risk > tranche_a * 0.055:
                risk = tranche_a * 0.055
                stop = tranche_a + risk
                lad_dict["stop_price"] = round(stop, 8)

            min_t1 = tranche_a - (2.0 * risk)
            if t1 > min_t1 or t1 <= 0:
                lad_dict["target_1_price"] = round(min_t1, 8)
                t1 = min_t1

            min_t2 = tranche_a - (4.0 * risk)
            if t2 > t1 or t2 <= 0:
                lad_dict["target_2_price"] = round(min_t2, 8)
                t2 = min_t2

            lad_dict["rr_a_t1"] = round(abs(tranche_a - t1) / risk, 2) if risk > 0 else 2.0
            lad_dict["rr_a_t2"] = round(abs(tranche_a - t2) / risk, 2) if risk > 0 else 4.0
        else:
            risk = tranche_a - stop
            # Clamp loose stop loss to max 5.5% of tranche_a (matches compute_ladder threshold)
            if risk > tranche_a * 0.055:
                risk = tranche_a * 0.055
                stop = tranche_a - risk
                lad_dict["stop_price"] = round(stop, 8)

            min_t1 = tranche_a + (2.0 * risk)
            if t1 < min_t1 or t1 <= 0:
                lad_dict["target_1_price"] = round(min_t1, 8)
                t1 = min_t1

            min_t2 = tranche_a + (4.0 * risk)
            if t2 < t1 or t2 <= 0:
                lad_dict["target_2_price"] = round(min_t2, 8)
                t2 = min_t2

            lad_dict["rr_a_t1"] = round(abs(t1 - tranche_a) / risk, 2) if risk > 0 else 2.0
            lad_dict["rr_a_t2"] = round(abs(t2 - tranche_a) / risk, 2) if risk > 0 else 4.0

    except Exception:
        pass

    return lad_dict
