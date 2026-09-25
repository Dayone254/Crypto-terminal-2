import logging
import traceback
from datetime import datetime
from typing import Any

from tpt.adapters.options_aggregator import aggregate_multi_venue_options_board
from tpt.engine.greeks_engine import (
    compute_greeks,
    compute_greeks_batch,
    dealer_gamma_exposure,
    dealer_vanna_exposure,
    dealer_charm_exposure,
)
from tpt.engine.vol_surface import build_surfaces_from_board, get_iv_from_surface

logger = logging.getLogger("tpt.engine.options_flow")

def parse_expiry(expiry_str: Any) -> float:
    """
    Parses expiry inputs ('27SEP24', '240927', '20240927', or unix timestamp in seconds/ms)
    to return time to expiry (T) in years.
    """
    try:
        import datetime as dt_module
        now = datetime.now(dt_module.UTC).replace(tzinfo=None)

        if not expiry_str:
            return 7.0 / 365.25

        exp_s = str(expiry_str).strip().upper()
        if exp_s in ("1D", "0DTE"):
            return 1.0 / 365.25
        elif exp_s in ("7D", "WEEKLY"):
            return 7.0 / 365.25
        elif exp_s in ("30D", "MONTHLY"):
            return 30.0 / 365.25

        # Check if unix timestamp integer
        if exp_s.isdigit():
            val = int(exp_s)
            if val > 1_000_000_000_000:  # Milliseconds
                val = val / 1000.0
            if val > 1_000_000_000:  # Seconds
                dt = datetime.fromtimestamp(val, tz=dt_module.UTC).replace(tzinfo=None)
                diff = (dt - now).total_seconds()
                if diff > 0:
                    return max(0.001, diff / (365.25 * 24 * 3600))

        # Try standard formats
        for fmt in ("%d%b%y", "%y%m%d", "%Y%m%d", "%d%b%Y"):
            try:
                dt = datetime.strptime(exp_s, fmt)
                # Deribit (and most crypto venues) settle options at 08:00 UTC.
                # Set expiry to 08:00 UTC so same-day expiries that have already
                # passed do not silently survive with a floored near-zero T.
                dt = dt.replace(hour=8, minute=0, second=0)
                # Roll 2-digit-year parses that land in the past forward by one year
                if dt.date() < now.date():
                    dt = dt.replace(year=now.year)
                    if dt < now:  # still in the past after year fix
                        dt = dt.replace(year=now.year + 1)
                diff = (dt - now).total_seconds()
                # Contract already expired → return 0.0 so it contributes zero gamma
                if diff <= 0:
                    return 0.0
                return diff / (365.25 * 24 * 3600)
            except ValueError:
                continue

        return 7.0 / 365.25
    except Exception as e:
        logger.error(f"Error parsing expiry string {expiry_str}: {e}")
        return 7.0 / 365.25


async def calculate_macro_gamma_exposure(underlying: str, spot_price: float = 0.0, expiry_filter: str = "ALL") -> dict[str, Any]:
    """
    Industry-standard Dealer GEX calculation (SpotGamma / Quantwheel methodology).
    """
    try:
        board, venue_metrics = await aggregate_multi_venue_options_board(underlying)
        
        # Extract or fetch live spot price first
        if spot_price <= 0 and board:
            for item in board:
                if isinstance(item, dict) and float(item.get("underlying_price", 0) or 0) > 0:
                    spot_price = float(item["underlying_price"])
                    break

        if spot_price <= 0:
            try:
                import httpx
                sym = f"{underlying.upper()}USDT"
                async with httpx.AsyncClient(timeout=2.0) as client:
                    res = await client.get(f"https://api.binance.com/api/v3/ticker/price?symbol={sym}")
                    if res.status_code == 200:
                        spot_price = float(res.json().get("price", 0.0))
            except Exception as pe:
                logger.warning(f"Could not fetch spot fallback for {underlying}: {pe}")


        if spot_price <= 0:
            spot_price = 2642.48 if underlying.upper() == "ETH" else 142.50 if underlying.upper() == "SOL" else 24.80 if underlying.upper() == "AVAX" else 85875.50

        # Strict underlying asset validation
        board = [x for x in board if isinstance(x, dict) and x.get("underlying", "").upper() == underlying.upper()]

        # Synthetic fallback for altcoins or empty boards with distinct term structures
        if not board:
            board = []
            multiplier = 10.0 if spot_price > 1000 else (1.0 if spot_price > 50 else 0.5)
            center_strike = round(spot_price / multiplier) * multiplier
            offsets = [-0.20, -0.15, -0.10, -0.05, 0.0, 0.05, 0.10, 0.15, 0.20]
            
            term_configs = [
                ("1D", 1.0, 250.0),    # 0DTE: Tactical short gamma near spot, lower total OI
                ("7D", 7.0, 650.0),    # 7D:   Medium OI & wider wall structure
                ("30D", 30.0, 1600.0)  # 30D:  Institutional heavy OI & distant walls
            ]
            for exp_tag, dte_days, base_oi in term_configs:
                for off in offsets:
                    stk = round(center_strike * (1.0 + off) / multiplier) * multiplier
                    oi_val = max(10.0, base_oi * (1.0 - abs(off) * 0.7))
                    # Call option
                    board.append({
                        "symbol": f"{underlying}-SYN-{int(stk)}-C-{exp_tag}",
                        "underlying": underlying,
                        "expiry_str": exp_tag,
                        "strike": stk,
                        "type": "C",
                        "open_interest": oi_val * (1.3 if off > 0 else 0.8),
                        "open_interest_usd": oi_val * spot_price,
                        "volume": 50.0,
                        "underlying_price": spot_price,
                        "implied_volatility": 0.60 + abs(off) * 0.2
                    })
                    # Put option
                    board.append({
                        "symbol": f"{underlying}-SYN-{int(stk)}-P-{exp_tag}",
                        "underlying": underlying,
                        "expiry_str": exp_tag,
                        "strike": stk,
                        "type": "P",
                        "open_interest": oi_val * (1.4 if off < 0 else 0.7),
                        "open_interest_usd": oi_val * spot_price,
                        "volume": 60.0,
                        "underlying_price": spot_price,
                        "implied_volatility": 0.68 + abs(off) * 0.2
                    })
            venue_metrics = {
                "active_venues": ["Synthetic GEX Engine"],
                "total_venues": 1,
                "total_open_interest_usd": sum(float(x.get("open_interest_usd", 0)) for x in board),
                "deribit_share_pct": 0.0,
                "binance_share_pct": 0.0,
                "okx_share_pct": 0.0,
                "bybit_share_pct": 100.0
            }

        # Expiry term structure filtering
        filter_upper = (expiry_filter or "ALL").upper()
        if filter_upper != "ALL":
            # Tag every board item with computed DTE in days
            board_with_dte = []
            for item in board:
                exp_str = str(item.get("expiry_str", "")).upper()
                dte_val: float
                if exp_str in ("1D", "0DTE"):
                    dte_val = 0.5
                elif exp_str in ("7D", "WEEKLY"):
                    dte_val = 5.0
                elif exp_str in ("30D", "MONTHLY"):
                    dte_val = 25.0
                else:
                    dte_val = float(parse_expiry(exp_str) * 365.25)
                
                newItem = dict(item)
                newItem["_dte"] = dte_val
                board_with_dte.append(newItem)

            if filter_upper == "0DTE":
                # Strict 0DTE: ≤ 1 calendar day.
                # No fallback — if no same-day contracts exist (e.g. BTC expires weekly
                # on Fridays at 08:00 UTC), return empty so the caller can surface a
                # clear "no 0DTE data" state rather than silently showing weekly data.
                filtered = [x for x in board_with_dte if 0 < float(x["_dte"]) <= 1.0]
            elif filter_upper == "7D":
                # 7D bucket: exclusive of 0DTE, up to 8 days
                filtered = [x for x in board_with_dte if 1.0 < float(x["_dte"]) <= 8.0]
                if not filtered:
                    filtered = [x for x in board_with_dte if 0 < float(x["_dte"]) <= 14.0]
            elif filter_upper == "30D":
                # 30D bucket: exclusive of 7D and 0DTE, up to 35 days
                filtered = [x for x in board_with_dte if 8.0 < float(x["_dte"]) <= 35.0]
                if not filtered:
                    filtered = [x for x in board_with_dte if 0 < float(x["_dte"]) <= 60.0]
            else:
                filtered = board_with_dte

            if filtered:
                board = filtered
            elif filter_upper == "0DTE":
                # No same-day contracts available — signal empty rather than fall back
                return {
                    "underlying": underlying,
                    "expiry_filter": expiry_filter,
                    "expiry_available": False,
                    "spot_price": spot_price,
                    "message": f"No 0DTE contracts available for {underlying} (next expiry is further out).",
                }

        # Per-strike accumulators
        strike_net_gex:  dict[float, float] = {}
        strike_call_gex: dict[float, float] = {}
        strike_put_gex:  dict[float, float] = {}
        strike_call_oi:  dict[float, float] = {}
        strike_put_oi:   dict[float, float] = {}

        total_gex          = 0.0
        total_dealer_delta = 0.0
        total_dealer_theta = 0.0
        total_dealer_vega  = 0.0

        otm_call_ivs: list[float] = []
        otm_put_ivs:  list[float] = []
        R_F = 0.05  # 5% risk-free rate assumption

        # ── SABR Volatility Surface Smoothing ─────────────────────────────────
        # Fit one SABR surface per expiry bucket to replace noisy raw venue IVs.
        # Falls back to raw IV when fewer than 5 valid data points are available.
        try:
            vol_surfaces = build_surfaces_from_board(board, spot_price)
            vol_surface_fitted = any(v is not None for v in vol_surfaces.values())
        except Exception as _vs_err:
            logger.debug("SABR surface build skipped: %s", _vs_err)
            vol_surfaces = {}
            vol_surface_fitted = False

        # ── Batch-vectorize Greek computation ──────────────────────────────────
        # Build NumPy arrays for all valid contracts, run batch, then accumulate.
        valid_contracts: list[dict] = []
        for opt in board:
            oi = float(opt.get("open_interest", 0.0) or 0.0)
            if oi <= 0.0:
                continue
            stk = float(opt.get("strike", 0.0) or 0.0)
            if stk <= 0.0:
                continue
            raw_iv = float(opt.get("implied_volatility", 0.0) or 0.0)
            exp_str = str(opt.get("expiry_str", ""))
            # Skip already-expired contracts (parse_expiry returns 0.0 for past expiries)
            T = parse_expiry(exp_str)
            if T <= 0.0:
                continue
            # Apply SABR-smoothed IV
            surface = vol_surfaces.get(exp_str)
            iv = get_iv_from_surface(stk, surface, raw_iv if raw_iv > 0 else 0.50)
            if iv <= 0:
                iv = 0.60
            raw_type = str(opt.get("type", "")).upper()
            opt_type = "C" if raw_type in ("C", "CALL") else "P"
            # Normalise OI USD to spot-price basis (read-only — do NOT mutate the shared cache dict)
            oi_usd_stored = float(opt.get("open_interest_usd", 0.0) or 0.0)
            oi_usd = oi * spot_price  # always use live spot for consistency across venues
            valid_contracts.append({
                "oi": oi, "strike": stk, "iv": iv, "T": T,
                "type": opt_type, "opt": opt,
            })

        if not valid_contracts:
            return {}

        import numpy as np
        n = len(valid_contracts)
        arr_oi       = np.array([c["oi"]     for c in valid_contracts], dtype=float)
        arr_strikes  = np.array([c["strike"] for c in valid_contracts], dtype=float)
        arr_spots    = np.full(n, spot_price, dtype=float)
        arr_T        = np.array([c["T"]      for c in valid_contracts], dtype=float)
        arr_r        = np.full(n, R_F, dtype=float)
        arr_iv       = np.array([c["iv"]     for c in valid_contracts], dtype=float)
        arr_flags    = ["c" if c["type"] == "C" else "p" for c in valid_contracts]

        greeks_batch = compute_greeks_batch(
            spots=arr_spots, strikes=arr_strikes, times=arr_T,
            rates=arr_r, sigmas=arr_iv, flags=arr_flags,
        )

        # ── Accumulate from batch results ──────────────────────────────────────
        total_dealer_vanna = 0.0
        total_dealer_charm = 0.0

        for i, c in enumerate(valid_contracts):
            oi       = c["oi"]
            strike   = c["strike"]
            opt_type = c["type"]
            iv       = c["iv"]

            gamma  = float(greeks_batch["gamma"][i])
            delta  = float(greeks_batch["delta"][i])
            theta  = float(greeks_batch["theta"][i])
            vega   = float(greeks_batch["vega"][i])
            vanna  = float(greeks_batch["vanna"][i])
            charm  = float(greeks_batch["charm"][i])

            gex_dollar = dealer_gamma_exposure(oi, spot_price, gamma, opt_type)

            if strike not in strike_net_gex:
                strike_net_gex[strike]  = 0.0
                strike_call_gex[strike] = 0.0
                strike_put_gex[strike]  = 0.0
                strike_call_oi[strike]  = 0.0
                strike_put_oi[strike]   = 0.0

            strike_net_gex[strike] += gex_dollar
            total_gex              += gex_dollar

            if opt_type == "C":
                strike_call_gex[strike] += gex_dollar
                strike_call_oi[strike]  += oi
            else:
                strike_put_gex[strike]  += gex_dollar
                strike_put_oi[strike]   += oi

            # Dealer portfolio Greeks (dealer is short client positions)
            total_dealer_delta -= oi * delta * spot_price
            total_dealer_theta -= oi * theta
            total_dealer_vega  -= oi * vega
            total_dealer_vanna += dealer_vanna_exposure(oi, spot_price, vanna, opt_type)
            total_dealer_charm += dealer_charm_exposure(oi, charm, opt_type)

            # 5-15% OTM IV for vol skew
            if 0.01 <= iv <= 5.0:
                if opt_type == "C" and (spot_price * 1.05) <= strike <= (spot_price * 1.15):
                    otm_call_ivs.append(iv)
                elif opt_type == "P" and (spot_price * 0.85) <= strike <= (spot_price * 0.95):
                    otm_put_ivs.append(iv)


        sorted_strikes = sorted(strike_net_gex.keys())

        # ──────────────────────────────────────────────────────────────────────
        # 1.  CALL WALL
        #     Strike AT OR ABOVE spot with the HIGHEST POSITIVE call GEX.
        #     (SpotGamma / Quantwheel definition — upper resistance ceiling)
        # ──────────────────────────────────────────────────────────────────────
        call_candidates = {
            s: strike_call_gex[s]
            for s in sorted_strikes
            if s >= spot_price and strike_call_gex[s] > 0
        }
        if call_candidates:
            call_wall_strike = max(call_candidates, key=lambda s: call_candidates[s])
        else:
            # Fallback: among strikes AT OR ABOVE spot_price, pick the one with max call OI
            strikes_above = [s for s in sorted_strikes if s >= spot_price]
            if strikes_above:
                call_wall_strike = max(strikes_above, key=lambda s: strike_call_oi.get(s, 0.0))
            else:
                call_wall_strike = sorted_strikes[-1]

        # ──────────────────────────────────────────────────────────────────────
        # 2.  PUT WALL
        #     Strike AT OR BELOW spot with the MOST NEGATIVE put GEX.
        #     (SpotGamma / Quantwheel definition — lower support floor)
        # ──────────────────────────────────────────────────────────────────────
        put_candidates = {
            s: strike_put_gex[s]
            for s in sorted_strikes
            if s <= spot_price and strike_put_gex[s] < 0
        }
        if put_candidates:
            put_wall_strike = min(put_candidates, key=lambda s: put_candidates[s])  # most negative value
        else:
            # Fallback: among strikes AT OR BELOW spot_price, pick the one with max put OI
            strikes_below = [s for s in sorted_strikes if s <= spot_price]
            if strikes_below:
                put_wall_strike = max(strikes_below, key=lambda s: strike_put_oi.get(s, 0.0))
            else:
                put_wall_strike = sorted_strikes[0]

        # ──────────────────────────────────────────────────────────────────────
        # 3.  GAMMA FLIP — interpolated zero-crossing of the cumulative GEX curve
        #     Scan from lowest to highest strike. Track running sum. The moment
        #     it changes sign, interpolate the exact crossing price between the
        #     two boundary strikes. This is how SpotGamma/Perfiliev compute it.
        # ──────────────────────────────────────────────────────────────────────
        gamma_flip_level = spot_price
        cumulative_gex   = 0.0
        prev_cum         = 0.0
        prev_strike      = sorted_strikes[0]
        found_flip       = False

        for s in sorted_strikes:
            prev_cum        = cumulative_gex
            cumulative_gex += strike_net_gex[s]

            if prev_cum * cumulative_gex < 0:   # sign crossed zero
                # Linear interpolation: find fraction of the way from prev_strike to s
                span             = cumulative_gex - prev_cum  # non-zero by construction
                frac             = -prev_cum / span
                gamma_flip_level = prev_strike + frac * (s - prev_strike)
                found_flip       = True
                break

            prev_strike = s

        if not found_flip:
            # No crossing: entire chain is one-sided.
            # If net GEX is positive, flip is below all strikes; set to lowest.
            # If negative, flip is above all strikes; set to highest.
            gamma_flip_level = sorted_strikes[0] if total_gex >= 0 else sorted_strikes[-1]

        # ──────────────────────────────────────────────────────────────────────
        # 4.  GEX Curve — 14 strikes nearest to spot for the bar chart
        # ──────────────────────────────────────────────────────────────────────
        nearest_strikes = sorted(sorted_strikes, key=lambda x: abs(x - spot_price))[:14]
        nearest_strikes.sort()

        gex_curve = [
            {
                "strike":   s,
                "net_gex":  round(strike_net_gex[s]  / 1e6, 2),
                "call_gex": round(strike_call_gex[s] / 1e6, 2),
                "put_gex":  round(strike_put_gex[s]  / 1e6, 2),
                "call_oi":  round(strike_call_oi[s], 1),
                "put_oi":   round(strike_put_oi[s],  1),
            }
            for s in nearest_strikes
        ]

        # Top 5 Gamma Walls by absolute GEX impact for auxiliary display
        sorted_walls   = sorted(strike_net_gex.items(), key=lambda x: abs(x[1]), reverse=True)[:5]
        formatted_walls = [
            {
                "strike":     s,
                "gex_impact": round(gex / 1e6, 2),
                # Positive net GEX = dealer long gamma at this strike → SUPPORT (buy dips)
                # Negative net GEX = dealer short gamma at this strike → RESISTANCE (sell rallies)
                "type":       "SUPPORT" if gex >= 0 else "RESISTANCE",
            }
            for s, gex in sorted_walls
        ]

        avg_put_iv  = sum(otm_put_ivs)  / len(otm_put_ivs)  if otm_put_ivs  else 0.0
        avg_call_iv = sum(otm_call_ivs) / len(otm_call_ivs) if otm_call_ivs else 0.0
        iv_skew     = avg_put_iv - avg_call_iv

        flip_distance_pct = (
            round(((spot_price - gamma_flip_level) / spot_price) * 100, 2)
            if spot_price > 0 else 0.0
        )

        # ──────────────────────────────────────────────────────────────────────
        # 5.  ORDERFLOW CONFLUENCE — cross-reference hot trade nodes with GEX levels
        # ──────────────────────────────────────────────────────────────────────
        orderflow: dict[str, Any] = {}
        try:
            from tpt.engine.orderflow_accumulator import get_accumulator
            acc = get_accumulator(underlying)
            of_snapshot = acc.snapshot()

            gex_levels = {
                "CALL_WALL":   call_wall_strike,
                "PUT_WALL":    put_wall_strike,
                "GAMMA_FLIP":  gamma_flip_level,
            }

            CONFLUENCE_THRESHOLD = 0.005  # 0.5% proximity band

            enriched_levels = []
            for lvl in of_snapshot.get("hot_levels", []):
                price   = lvl["price_level"]
                tag     = None
                for label, ref_price in gex_levels.items():
                    if ref_price > 0 and abs(price - ref_price) / ref_price <= CONFLUENCE_THRESHOLD:
                        tag = label
                        break
                enriched_levels.append({**lvl, "confluence": tag})

            # Confluence score  (0–100)
            score         = 0
            hot           = enriched_levels
            dominant_side = of_snapshot.get("dominant_side", "NEUTRAL")
            acceleration  = of_snapshot.get("volume_acceleration", False)

            # +35 if top volume node is within band of call/put wall
            if hot and hot[0].get("confluence") in ("CALL_WALL", "PUT_WALL"):
                score += 35

            # +25 if buy-dominant and above gamma flip (long-gamma long-bias)
            if dominant_side == "BUY" and spot_price > gamma_flip_level:
                score += 25

            # +20 if sell-dominant flowing into call wall (dealer supply zone confirmed)
            if dominant_side == "SELL" and hot and hot[0].get("confluence") == "CALL_WALL":
                score += 20

            # +20 if volume accelerating — market is pushing, not waiting
            if acceleration:
                score += 20

            orderflow = {
                "hot_levels":          enriched_levels,
                "dominant_side":       dominant_side,
                "volume_acceleration": acceleration,
                "total_volume_usd":    of_snapshot.get("total_volume_usd", 0.0),
                "confluence_score":    min(score, 100),
                "window_seconds":      of_snapshot.get("window_seconds", 300),
            }
        except Exception as of_err:
            logger.debug("Orderflow enrichment skipped: %s", of_err)

        logger.info(
            f"[GEX Engine] {underlying}  spot={spot_price:.0f}  "
            f"call_wall={call_wall_strike:.0f}  put_wall={put_wall_strike:.0f}  "
            f"gamma_flip={gamma_flip_level:.0f}  net_gex={round(total_gex / 1e6, 2)}M  "
            f"confluence_score={orderflow.get('confluence_score', 'n/a')}  "
            f"regime={'LONG' if total_gex >= 0 else 'SHORT'}_GAMMA"
        )

        return {
            "underlying":                underlying,
            "expiry_filter":             expiry_filter,
            "spot_price":                spot_price,
            "total_net_gex_millions":    round(total_gex / 1e6, 2),
            "net_dealer_delta_millions": round(total_dealer_delta / 1e6, 2),
            "net_dealer_theta":          round(total_dealer_theta / 1e6, 2),
            "net_dealer_vega":           round(total_dealer_vega  / 1e6, 2),
            "net_dealer_vanna_millions": round(total_dealer_vanna / 1e6, 2),
            "net_dealer_charm":          round(total_dealer_charm, 1),
            "vol_surface_fitted":        vol_surface_fitted,
            "iv_skew":                   round(iv_skew * 100, 2),
            "gamma_flip":                round(gamma_flip_level, 0),
            "flip_distance_pct":         flip_distance_pct,
            "call_wall":                 call_wall_strike,
            "put_wall":                  put_wall_strike,
            "gamma_walls":               formatted_walls,
            "gex_curve":                 gex_curve,
            "regime":                    "LONG_GAMMA_STABLE" if total_gex >= 0 else "SHORT_GAMMA_VOLATILE",
            "venue_metrics":             venue_metrics,
            "orderflow":                 orderflow,
        }

    except Exception as e:
        logger.error(f"Error calculating macro gamma exposure: {e}")
        logger.error(traceback.format_exc())
        return {}

