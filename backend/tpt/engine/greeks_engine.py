import math


def norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function using math.erf"""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def norm_pdf(x: float) -> float:
    """Standard normal probability density function"""
    return math.exp(-0.5 * x**2) / math.sqrt(2.0 * math.pi)

def calculate_d1_d2(S: float, K: float, T: float, r: float, sigma: float):
    """
    S: Spot mark price
    K: Strike price
    T: Time to expiry in years
    r: Risk-free interest rate (e.g., 0.05)
    sigma: Implied volatility (e.g., 0.60)
    """
    if T <= 0 or sigma <= 0:
        return 0.0, 0.0
    
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return d1, d2

def compute_greeks(S: float, K: float, T: float, r: float, sigma: float, option_type: str = "C"):
    """
    Computes Delta, Gamma, Theta, Vega for an option.
    Returns dict of greeks.
    """
    if T <= 0.0001 or sigma <= 0:
        return {"delta": 0, "gamma": 0, "theta": 0, "vega": 0}
        
    d1, d2 = calculate_d1_d2(S, K, T, r, sigma)
    
    # Delta
    if option_type == "C":
        delta = norm_cdf(d1)
    else:
        delta = norm_cdf(d1) - 1.0
        
    # Gamma (Same for Call and Put)
    gamma = norm_pdf(d1) / (S * sigma * math.sqrt(T))
    
    # Vega (Same for Call and Put)
    vega = S * norm_pdf(d1) * math.sqrt(T)
    
    # Theta
    term1 = -(S * norm_pdf(d1) * sigma) / (2 * math.sqrt(T))
    if option_type == "C":
        theta = term1 - r * K * math.exp(-r*T) * norm_cdf(d2)
    else:
        theta = term1 + r * K * math.exp(-r*T) * norm_cdf(-d2)
        
    # Convert theta / vega to daily conventions 
    return {
        "delta": delta,
        "gamma": gamma,
        "theta": theta / 365.0,
        "vega": vega / 100.0
    }

def dealer_gamma_exposure(open_interest: float, S: float, gamma: float, option_type: str = "C", is_dealer_long: bool = False):
    """
    Calculates the Dealer Gamma Exposure (GEX) for a specific strike.
    Assuming dealers are short calls (retail buys calls) and short puts (retail buys puts) as default positioning.
    """
    # Contract multiplier in crypto is usually 1, but we multiply by Spot for Dollar Gamma.
    # $GEX = Open_Interest * Gamma * 100 * Spot_Price^2 / 100
    # A cleaner dollar gamma proxy per 1% move:
    dollar_gamma = (gamma * S * S * 0.01) * open_interest
    
    # If the dealer sold the option (short), their gamma is negative.
    # By default, Market Makers are generally assumed to be short the options retail buys.
    if is_dealer_long:
        return dollar_gamma
    else:
        return -dollar_gamma
