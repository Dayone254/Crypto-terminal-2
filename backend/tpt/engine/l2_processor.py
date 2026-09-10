from typing import Any


def process_l2_book(raw_book: dict[str, Any]) -> dict[str, Any]:
    """
    Processes a raw Binance partial orderbook.
    Computes imbalance ratio and detects large liquidity walls.
    """
    # Raw book format: "bids": [[price_str, qty_str], ...], "asks": ...
    bids: list[list[float]] = []
    asks: list[list[float]] = []
    
    total_bid_vol_usd = 0.0
    total_ask_vol_usd = 0.0
    
    buy_walls = []
    sell_walls = []
    
    WALL_THRESHOLD_USD = 50_000  # $50k USD constitutes an institutional wall
    
    # Process Bids
    for b in raw_book.get("bids", []):
        price = float(b[0])
        qty = float(b[1])
        vol_usd = price * qty
        total_bid_vol_usd += vol_usd
        
        bids.append([price, qty, vol_usd])
        if vol_usd >= WALL_THRESHOLD_USD:
            buy_walls.append({"price": price, "vol_usd": vol_usd})
            
    # Process Asks
    for a in raw_book.get("asks", []):
        price = float(a[0])
        qty = float(a[1])
        vol_usd = price * qty
        total_ask_vol_usd += vol_usd
        
        asks.append([price, qty, vol_usd])
        if vol_usd >= WALL_THRESHOLD_USD:
            sell_walls.append({"price": price, "vol_usd": vol_usd})

    # Imbalance Ratio
    total_vol = total_bid_vol_usd + total_ask_vol_usd
    imbalance_ratio = 0.5
    if total_vol > 0:
        imbalance_ratio = total_bid_vol_usd / total_vol
        
    return {
        "bids": bids,
        "asks": asks,
        "metrics": {
            "total_bid_vol_usd": total_bid_vol_usd,
            "total_ask_vol_usd": total_ask_vol_usd,
            "imbalance_ratio": imbalance_ratio,
            "buy_walls": buy_walls,
            "sell_walls": sell_walls,
        }
    }
