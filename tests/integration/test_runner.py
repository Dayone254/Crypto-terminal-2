"""Integration tests for scanner/runner.py using a mocked CoinbaseAdapter."""
import httpx
import pytest
from sqlalchemy import func, select

from tpt.adapters.coinbase import CoinbaseAdapter
from tpt.db.connection import AsyncSessionLocal
from tpt.db.models import Feature, Ladder, ScanRun, Score, Snapshot
from tpt.scanner.runner import run_scan


@pytest.fixture
def mock_adapter() -> CoinbaseAdapter:
    products_json = [
        {"id": "BTC-USD", "base_currency": "BTC", "quote_currency": "USD", "status": "online", "trading_disabled": False},
        {"id": "ZORA-USD", "base_currency": "ZORA", "quote_currency": "USD", "status": "online", "trading_disabled": False},
    ]

    stats_btc = {"open": "80000.0", "high": "85000.0", "low": "79000.0", "last": "84000.0", "volume": "5000"}
    ticker_btc = {"price": "84000.0", "bid": "83990.0", "ask": "84010.0", "volume": "5000"}

    stats_zora = {"open": "0.0081", "high": "0.00995", "low": "0.0076", "last": "0.00852", "volume": "1200000000"}
    ticker_zora = {"price": "0.00852", "bid": "0.00851", "ask": "0.00853", "volume": "1200000000"}

    # Mock candles [time, low, high, open, close, volume]
    candles_sample = [
        [1725500000 + i * 3600, 0.0080, 0.0088, 0.0081, 0.0085, 5000000]
        for i in range(20)
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/products":
            return httpx.Response(200, json=products_json)
        elif path == "/products/BTC-USD/stats":
            return httpx.Response(200, json=stats_btc)
        elif path == "/products/BTC-USD/ticker":
            return httpx.Response(200, json=ticker_btc)
        elif path == "/products/ZORA-USD/stats":
            return httpx.Response(200, json=stats_zora)
        elif path == "/products/ZORA-USD/ticker":
            return httpx.Response(200, json=ticker_zora)
        elif "/candles" in path:
            return httpx.Response(200, json=candles_sample)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return CoinbaseAdapter(client=client)


@pytest.mark.asyncio
async def test_run_scan_mocked(mock_adapter: CoinbaseAdapter) -> None:
    adapter = mock_adapter
    try:
        res = await run_scan(trigger="ON_DEMAND", adapter=adapter)
        assert res.status == "DONE"
        assert res.symbols_fetched == 2
        assert res.candidates_count == 2
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_run_scan_persists_results(mock_adapter: CoinbaseAdapter) -> None:
    """Regression: the scan session used to never commit, so every feature /
    score / snapshot was rolled back and the dashboard stayed empty."""
    adapter = mock_adapter
    try:
        res = await run_scan(trigger="ON_DEMAND", adapter=adapter)
        assert res.status == "DONE"

        async with AsyncSessionLocal() as db:
            run = await db.get(ScanRun, res.scan_run_id)
            assert run is not None
            assert run.status == "DONE"
            assert run.symbols_fetched == 2

            for model in (Snapshot, Feature, Score):
                count = await db.execute(
                    select(func.count()).select_from(model).where(model.scan_run_id == res.scan_run_id)
                )
                assert count.scalar_one() == 2, f"{model.__name__} rows were not committed"

            # At least one candidate must produce a ladder row.
            ladders = await db.execute(
                select(func.count()).select_from(Ladder).where(Ladder.scan_run_id == res.scan_run_id)
            )
            assert ladders.scalar_one() >= 1
    finally:
        await adapter.close()
