from typing import Any
from tpt.engine.l2_wall_analyzer import wall_analyzer

def process_l2_book(raw_book: dict[str, Any]) -> dict[str, Any]:
    """
    Processes an aggregated multi-exchange orderbook frame (Coinbase, Binance, Kraken, OKX, Bybit).
    Computes USD volumes, detects institutional walls, and extracts multi-venue support/resistance.
    """
    bids: list[list[float]] = []
    asks: list[list[float]] = []

    total_bid_vol_usd = 0.0
    total_ask_vol_usd = 0.0

    WALL_THRESHOLD_USD = 50_000
    buy_walls = []
    sell_walls = []

    # Process Bids
    for b in raw_book.get("bids", []):
        try:
            price = float(b[0])
            qty = float(b[1])
            vol_usd = price * qty
            total_bid_vol_usd += vol_usd
            bids.append([price, qty, vol_usd])
            if vol_usd >= WALL_THRESHOLD_USD:
                buy_walls.append({"price": price, "vol_usd": vol_usd})
        except (ValueError, TypeError, IndexError):
            continue

    # Process Asks
    for a in raw_book.get("asks", []):
        try:
            price = float(a[0])
            qty = float(a[1])
            vol_usd = price * qty
            total_ask_vol_usd += vol_usd
            asks.append([price, qty, vol_usd])
            if vol_usd >= WALL_THRESHOLD_USD:
                sell_walls.append({"price": price, "vol_usd": vol_usd})
        except (ValueError, TypeError, IndexError):
            continue

    # Multi-Venue Wall & Level Analysis
    wall_analysis = wall_analyzer.analyze_book(raw_book)

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
            "support_levels": wall_analysis["support_levels"],
            "resistance_levels": wall_analysis["resistance_levels"],
            "institutional_bias": wall_analysis["institutional_bias"],
            "major_bid_wall": wall_analysis["major_bid_wall"],
            "major_ask_wall": wall_analysis["major_ask_wall"],
            "active_exchanges": wall_analysis["active_exchanges"],
            "total_venues": wall_analysis["total_venues"]
        }
    }
