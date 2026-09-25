"""TapeRadar V2.0 Multi-Factor Composite Setup Scoring Strategy."""
from __future__ import annotations

from typing import Any

from tpt.config.strategy import StrategyConfig, load_strategy
from tpt.engine.features import compute_features
from tpt.engine.labeler import label
from tpt.engine.ladder import compute_ladder
from tpt.engine.scorer import score
from tpt.strategies.base import BaseStrategy


class TapeRadarV2Strategy(BaseStrategy):
    """Default TapeRadar V2.0 composite quantitative scoring strategy."""

    strategy_id: str = "taperadar_v2"
    name: str = "TapeRadar V2.0 Composite Scorer"
    description: str = "Multi-factor composite quantitative scanner evaluating momentum, relative strength, RSI, and orderbook structure."
    author: str = "TapeRadar Core"
    version: str = "2.0.0"

    def __init__(self, config: StrategyConfig | None = None) -> None:
        self.config = config or load_strategy()

    def evaluate_signal(
        self,
        symbol: str,
        candles_15m: list[list[Any]],
        candles_1h: list[list[Any]] | None = None,
        btc_candles_1h: list[list[Any]] | None = None,
    ) -> dict[str, Any] | None:
        candles_1h = candles_1h or candles_15m
        if not candles_1h or len(candles_1h) < 30:
            return None

        features = compute_features(
            symbol=symbol,
            raw_candles_1h=candles_1h,
            raw_candles_15m=candles_15m,
            btc_candles_1h=btc_candles_1h,
        )
        scored = score(features, self.config)
        labeled = label(scored, self.config)

        if labeled.label not in ("ENTRY_ZONE", "COILED"):
            return None

        last_price = float(candles_1h[-1][4])
        ladder = compute_ladder(
            symbol=symbol,
            side=labeled.side,
            entry_price=last_price,
            config=self.config,
        )

        return {
            "symbol": symbol,
            "side": labeled.side,
            "label": labeled.label,
            "composite_score": labeled.composite_score,
            "entry_price": last_price,
            "stop_loss": ladder.stop_loss,
            "take_profit_1": ladder.take_profit_1,
            "take_profit_2": ladder.take_profit_2,
            "strategy_id": self.strategy_id,
            "strategy_name": self.name,
            "score_breakdown": labeled.score_breakdown,
        }
