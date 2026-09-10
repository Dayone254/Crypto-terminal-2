"""Abstract base class for exchange adapters."""
from abc import ABC, abstractmethod


class ExchangeAdapter(ABC):
    """Interface all exchange adapters must implement."""

    @abstractmethod
    async def get_products(self) -> list[dict]:
        """Return list of tradeable product dicts."""
        ...

    @abstractmethod
    async def get_stats(self, product_id: str) -> dict:
        """Return 24h OHLCV statistics for a product."""
        ...

    @abstractmethod
    async def get_ticker(self, product_id: str) -> dict:
        """Return latest price/bid/ask/volume for a product."""
        ...

    @abstractmethod
    async def get_candles(
        self, product_id: str, granularity: int, limit: int = 50
    ) -> list[list]:
        """Return OHLCV candles. granularity in seconds (3600=1h, 86400=1d)."""
        ...
