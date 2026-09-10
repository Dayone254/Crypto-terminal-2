import logging
import traceback
from datetime import datetime
from typing import Any

from tpt.adapters.deribit_options import aggregate_options_board
from tpt.engine.greeks_engine import compute_greeks, dealer_gamma_exposure

logger = logging.getLogger("tpt.engine.options_flow")

def parse_expiry(expiry_str: str) -> float:
    """
    Parses '27SEP24' (DDMMMYY) to return time to expiry (T) in years.
    """
    try:
        dt = datetime.strptime(expiry_str.upper(), "%d%b%y")
        import datetime as dt_module
        now = datetime.now(dt_module.UTC).replace(tzinfo=None)
        diff = (dt - now).total_seconds()
        return max(0.0001, diff / (365.25 * 24 * 3600))
    except Exception as e:
        logger.error(f"Error parsing expiry string {expiry_str}: {e}")
        return 0.0001

async def calculate_macro_gamma_exposure(underlying: str, spot_price: float) -> dict[str, Any]:
    """
    Given the current live spot price (from Coinbase), this function pulls the full 
    Options Board from Binance, calculates Greek exposures for every strike, 
    and determines the Net Gamma Exposure (GEX) and the Gamma Flip location.
    """
    try:
        board = await aggregate_options_board(underlying)
        if not board:
            return {}

        if spot_price <= 0.0:
            spot_price = board[0].get("underlying_price", spot_price)
            if spot_price <= 0:
                logger.error("No valid spot price for Greeks Engine!")
                return {}

        strike_gamma = {}
        total_gex = 0.0
        total_dealer_delta = 0.0
        total_dealer_theta = 0.0
        total_dealer_vega = 0.0
        
        otm_call_ivs = []
        otm_put_ivs = []
        
        # Risk-free rate assumption (Standard baseline 5% = 0.05)
        R_F = 0.05
        
        highest_gamma_strike = 0
        max_gamma = -9999999999.0
        
        for opt in board:
            open_interest = opt["open_interest"]
            if open_interest <= 0:
                continue
                
            T = parse_expiry(opt["expiry_str"])
            iv = opt["implied_volatility"]
            
            iv_valid = True
            if iv <= 0:
                # If Binance IV is 0 or missing, default to a flat baseline for estimation (e.g. 50%)
                iv = 0.50
                iv_valid = False
                
            greeks = compute_greeks(
                S=spot_price,
                K=opt["strike"],
                T=T,
                r=R_F,
                sigma=iv,
                option_type=opt["type"]
            )
            
            gamma = greeks.get("gamma", 0)
            
            # Dealer GEX assumption: dealers are short options bought by retail.
            gex_dollar = dealer_gamma_exposure(open_interest, spot_price, gamma, opt["type"])
            
            strike = opt["strike"]
            if strike not in strike_gamma:
                strike_gamma[strike] = 0.0
                
            strike_gamma[strike] += gex_dollar
            total_gex += gex_dollar
            
            # Dealer Greek Aggregation (assuming dealers are short the retail volume)
            # Delta is expressed nominally in USD exposure
            total_dealer_delta -= open_interest * greeks.get("delta", 0) * spot_price
            total_dealer_theta -= open_interest * greeks.get("theta", 0)
            total_dealer_vega -= open_interest * greeks.get("vega", 0)
            
            # 5-15% OTM IV extraction for Volatility Skew
            if iv_valid:
                if opt["type"] == "C" and (spot_price * 1.05) <= strike <= (spot_price * 1.15):
                    otm_call_ivs.append(iv)
                elif opt["type"] == "P" and (spot_price * 0.85) <= strike <= (spot_price * 0.95):
                    otm_put_ivs.append(iv)
            
        # Find the Gamma Wall (Strike with the largest absolute gamma magnitude)
        # Find the Gamma Flip (Usually the strike where Net Dealer Gamma is heavily negative vs positive)
        # For a simplified TapeRadar map, we just return strikes sorted by highest GEX absolute impact
        sorted_strikes = sorted(strike_gamma.items(), key=lambda x: abs(x[1]), reverse=True)
        
        # Select top 5 strikes to act as Support/Resistance boundaries (Gamma Walls)
        top_walls = sorted_strikes[:5]
        
        formatted_walls = []
        for s, gex in top_walls:
            formatted_walls.append({
                "strike": s,
                "gex_impact": gex,
                "type": "RESISTANCE" if gex < 0 else "SUPPORT"  # Negative GEX enforces volatility, Positive GEX suppresses it
            })

        avg_put_iv = sum(otm_put_ivs) / len(otm_put_ivs) if otm_put_ivs else 0.0
        avg_call_iv = sum(otm_call_ivs) / len(otm_call_ivs) if otm_call_ivs else 0.0
        iv_skew = avg_put_iv - avg_call_iv  # Positive = Puts cost more (Fear), Negative = Calls cost more (Greed)

        return {
            "total_net_gex": total_gex,
            "net_dealer_delta": total_dealer_delta,
            "net_dealer_theta": total_dealer_theta,
            "net_dealer_vega": total_dealer_vega,
            "iv_skew": iv_skew,
            "gamma_walls": formatted_walls,
            "gamma_flip": top_walls[0][0] if top_walls else spot_price
        }

    except Exception as e:
        logger.error(f"Error calculating macro gamma exposure: {e}")
        logger.error(traceback.format_exc())
        return {}
