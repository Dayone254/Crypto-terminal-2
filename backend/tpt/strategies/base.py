"""Base Strategy abstract interface for pluggable TapeRadar strategies."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseStrategy(ABC):
    """Abstract Base Class for all TapeRadar strategy plugins."""

    strategy_id: str = "base_strategy"
    name: str = "Base Strategy"
    description: str = "Abstract strategy template."
    author: str = "TapeRadar Core"
    version: str = "1.0.0"

    @abstractmethod
    def evaluate_signal(
        self,
        symbol: str,
        candles_15m: list[list[Any]],
        candles_1h: list[list[Any]] | None = None,
        btc_candles_1h: list[list[Any]] | None = None,
    ) -> dict[str, Any] | None:
        """
        Evaluate candle series up to current bar timestamp.

        Args:
            symbol: Trading pair identifier (e.g. 'BTC-USD')
            candles_15m: 15-minute OHLCV candles [[ts, open, high, low, close, vol], ...]
            candles_1h: 1h OHLCV candles
            btc_candles_1h: BTC 1h benchmark candles

        Returns:
            dict containing setup details if triggered (ENTRY_ZONE or COILED), else None.
        """
        pass

    def to_dict(self) -> dict[str, Any]:
        """Serialize strategy metadata for API & Dashboard discovery."""
        return {
            "strategy_id": self.strategy_id,
            "name": self.name,
            "description": self.description,
            "author": self.author,
            "version": self.version,
        }
