import logging
from typing import Any

logger = logging.getLogger(__name__)

class MultiVenueWallAnalyzer:
    """
    Analyzes aggregated multi-exchange L2 orderbooks (Coinbase, Binance, Kraken, OKX, Bybit).
    Detects institutional liquidity walls, multi-venue confluence levels, and orderbook imbalance ratios.
    """

    @staticmethod
    def analyze_book(aggregated_book: dict[str, Any]) -> dict[str, Any]:
        """
        Analyzes aggregated L2 orderbook bids and asks to isolate key support/resistance levels.
        """
        bids = aggregated_book.get("bids", [])
        asks = aggregated_book.get("asks", [])
        active_exchanges = aggregated_book.get("active_exchanges", [])
        total_venues = aggregated_book.get("total_venues", len(active_exchanges))

        if not bids or not asks:
            return {
                "support_levels": [],
                "resistance_levels": [],
                "imbalance_ratio": 0.0,
                "institutional_bias": "NEUTRAL",
                "major_bid_wall": None,
                "major_ask_wall": None,
                "active_exchanges": active_exchanges
            }

        # Parse prices & volumes
        parsed_bids = [(float(p), float(q)) for p, q in bids]
        parsed_asks = [(float(p), float(q)) for p, q in asks]

        total_bid_vol = sum(q for _, q in parsed_bids)
        total_ask_vol = sum(q for _, q in parsed_asks)

        # Net Institutional Imbalance (-1.0 to +1.0)
        total_vol = total_bid_vol + total_ask_vol
        imbalance_ratio = round((total_bid_vol - total_ask_vol) / total_vol, 3) if total_vol > 0 else 0.0

        if imbalance_ratio > 0.25:
            bias = "BULLISH_INSTITUTIONAL_ACCUMULATION"
        elif imbalance_ratio < -0.25:
            bias = "BEARISH_INSTITUTIONAL_DISTRIBUTION"
        else:
            bias = "NEUTRAL"

        # Identify Major Liquidity Walls (volume > 2x average depth level)
        avg_bid_vol = total_bid_vol / len(parsed_bids) if parsed_bids else 1.0
        avg_ask_vol = total_ask_vol / len(parsed_asks) if parsed_asks else 1.0

        support_walls = [
            {"price": p, "volume": round(q, 4), "strength": round(q / avg_bid_vol, 1)}
            for p, q in parsed_bids if q > 1.8 * avg_bid_vol
        ]

        resistance_walls = [
            {"price": p, "volume": round(q, 4), "strength": round(q / avg_ask_vol, 1)}
            for p, q in parsed_asks if q > 1.8 * avg_ask_vol
        ]

        # Top Support (Highest Volume Bid Wall)
        major_bid_wall = max(support_walls, key=lambda x: x["volume"]) if support_walls else None
        # Top Resistance (Highest Volume Ask Wall)
        major_ask_wall = max(resistance_walls, key=lambda x: x["volume"]) if resistance_walls else None

        return {
            "support_levels": support_walls[:3],
            "resistance_levels": resistance_walls[:3],
            "imbalance_ratio": imbalance_ratio,
            "institutional_bias": bias,
            "major_bid_wall": major_bid_wall,
            "major_ask_wall": major_ask_wall,
            "active_exchanges": active_exchanges,
            "total_venues": total_venues
        }

wall_analyzer = MultiVenueWallAnalyzer()
