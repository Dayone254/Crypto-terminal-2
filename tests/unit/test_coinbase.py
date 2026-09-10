"""Unit tests for CoinbaseExchangeAdapter using httpx MockTransport."""
import asyncio

import httpx
import pytest

from tpt.adapters.coinbase import CoinbaseAdapter, TokenBucketRateLimiter


@pytest.mark.asyncio
async def test_token_bucket_rate_limiter() -> None:
    limiter = TokenBucketRateLimiter(rate=10.0)
    start = asyncio.get_event_loop().time()
    for _ in range(5):
        await limiter.acquire()
    elapsed = asyncio.get_event_loop().time() - start
    assert elapsed < 1.0


@pytest.mark.asyncio
async def test_coinbase_adapter_get_products() -> None:
    mock_payload = [
        {"id": "BTC-USD", "quote_currency": "USD", "status": "online", "trading_disabled": False},
        {"id": "ETH-EUR", "quote_currency": "EUR", "status": "online", "trading_disabled": False},
        {"id": "SOL-USD", "quote_currency": "USD", "status": "offline", "trading_disabled": False},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/products":
            return httpx.Response(200, json=mock_payload)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    adapter = CoinbaseAdapter(client=client)

    try:
        products = await adapter.get_products()
        assert len(products) == 1
        assert products[0]["id"] == "BTC-USD"
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_coinbase_adapter_retry_backoff() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429)
        return httpx.Response(200, json={"price": "85000.00"})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    adapter = CoinbaseAdapter(client=client)

    try:
        ticker = await adapter.get_ticker("BTC-USD")
        assert ticker["price"] == "85000.00"
        assert calls == 2
    finally:
        await adapter.close()
