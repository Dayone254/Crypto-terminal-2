"""Coinbase exchange adapter — public REST API (no auth).

Handles rate limiting (token bucket 3 req/s), concurrency semaphore (10),
and exponential backoff retry on HTTP 429 and network errors.
"""
from __future__ import annotations

import asyncio
import time
from datetime import UTC
from typing import Any

import httpx

from tpt.adapters.base import ExchangeAdapter


class TokenBucketRateLimiter:
    """Async token bucket rate limiter."""

    def __init__(self, rate: float = 3.0) -> None:
        self._rate = rate
        self._tokens = rate
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        wait_time = 0.0
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._rate, self._tokens + elapsed * self._rate)
            self._last_refill = now
            if self._tokens < 1.0:
                wait_time = (1.0 - self._tokens) / self._rate
                self._tokens = 0.0 # Will take 1 token after waking, or count it now as negative
                # Better: calculate the time, and temporarily reserve it
                self._tokens -= 1.0
            else:
                self._tokens -= 1.0
        if wait_time > 0:
            await asyncio.sleep(wait_time)


class CoinbaseAdapter(ExchangeAdapter):
    """Fetches public market data from Coinbase Exchange REST API."""

    BASE_URL = "https://api.exchange.coinbase.com"

    def __init__(
        self,
        base_url: str = BASE_URL,
        rate_limit: float = 9.0,
        max_concurrency: int = 10,
        timeout: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.rate_limiter = TokenBucketRateLimiter(rate=rate_limit)
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.timeout = timeout
        self._client = client
        self._own_client = client is None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": "TopPickerTerminal/1.0"},
                timeout=httpx.Timeout(self.timeout),
            )
            self._own_client = True
        return self._client

    async def close(self) -> None:
        if self._own_client and self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    async def _request(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """Execute rate-limited request with retry and exponential backoff."""
        client = await self._get_client()
        url = f"{self.base_url}{endpoint}"
        max_retries = 3

        for attempt in range(max_retries + 1):
            await self.rate_limiter.acquire()
            async with self.semaphore:
                try:
                    response = await client.get(url, params=params)
                    if response.status_code == 429 and attempt < max_retries:
                        backoff = min(60.0, (2.0 ** attempt) * 2.0)
                        await asyncio.sleep(backoff)
                        continue
                    response.raise_for_status()
                    return response.json()
                except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                    if attempt < max_retries:
                        backoff = min(60.0, (2.0 ** attempt) * 2.0)
                        await asyncio.sleep(backoff)
                    else:
                        raise exc

    async def get_products(self) -> list[dict[str, Any]]:
        """Return active USD spot products."""
        data = await self._request("/products")
        if not isinstance(data, list):
            return []
        usd_products = [
            p for p in data
            if isinstance(p, dict)
            and p.get("quote_currency") == "USD"
            and p.get("status") == "online"
            and not p.get("trading_disabled", False)
        ]
        return usd_products

    async def get_stats(self, product_id: str) -> dict[str, Any]:
        """Return 24h OHLCV stats for product."""
        res = await self._request(f"/products/{product_id}/stats")
        return res if isinstance(res, dict) else {}

    async def get_ticker(self, product_id: str) -> dict[str, Any]:
        """Return latest ticker for product."""
        res = await self._request(f"/products/{product_id}/ticker")
        return res if isinstance(res, dict) else {}

    async def get_candles(
        self,
        product_id: str,
        granularity: int,
        limit: int = 50,
        start: str | int | float | None = None,
        end: str | int | float | None = None,
    ) -> list[list[Any]]:
        """Return OHLCV candles array (newest first from Coinbase).
        
        Coinbase granularity in seconds: 60 = 1m, 300 = 5m, 900 = 15m, 3600 = 1h, 86400 = 1d.
        """
        params: dict[str, Any] = {"granularity": granularity}
        if start is not None:
            if isinstance(start, (int, float)):
                from datetime import datetime
                params["start"] = datetime.fromtimestamp(start, tz=UTC).isoformat()
            else:
                params["start"] = str(start)
        if end is not None:
            if isinstance(end, (int, float)):
                from datetime import datetime
                params["end"] = datetime.fromtimestamp(end, tz=UTC).isoformat()
            else:
                params["end"] = str(end)

        # Explicitly request limit (Coinbase supports max 300)
        params["limit"] = min(limit, 300)

        res = await self._request(f"/products/{product_id}/candles", params=params)
        if isinstance(res, list):
            return res[:limit]
        return []

    async def get_l2_snapshot(self, product_id: str) -> dict[str, Any]:
        """Return level 2 orderbook snapshot."""
        res = await self._request(f"/products/{product_id}/book", params={"level": 2})
        return res if isinstance(res, dict) else {}

    async def get_candles_15m(
        self, product_id: str, limit: int = 50
    ) -> list[list[Any]]:
        """Return 15-minute OHLCV candles (newest first)."""
        return await self.get_candles(product_id, granularity=900, limit=limit)

    async def get_candles_4h(
        self, product_id: str, limit: int = 60
    ) -> list[list[Any]]:
        """Return 4-hour OHLCV candles (newest first). Default 60 = 10 days."""
        return await self.get_candles(product_id, granularity=14400, limit=limit)
