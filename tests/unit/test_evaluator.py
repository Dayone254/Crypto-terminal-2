from unittest.mock import AsyncMock, patch

import httpx
import pytest

from tpt.adapters.coinbase import CoinbaseAdapter
from tpt.engine.evaluator import _resolve_same_candle_collision


@pytest.mark.asyncio
async def test_coinbase_adapter_candles_with_start_end():
    adapter = CoinbaseAdapter()
    with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = [[1700000000, 100, 105, 101, 104, 50]]
        candles = await adapter.get_candles("BTC-USD", granularity=60, limit=15, start=1700000000, end=1700000900)
        assert len(candles) == 1
        mock_req.assert_called_once()
        call_params = mock_req.call_args[1]["params"]
        assert call_params["granularity"] == 60
        assert "start" in call_params
        assert "end" in call_params
    await adapter.close()


@pytest.mark.asyncio
async def test_resolve_same_candle_collision_long_tp_first():
    """Verify that when 1m candles show TP hit at minute 2 before SL, status is WIN."""
    client = AsyncMock(spec=httpx.AsyncClient)
    
    # 15m candle timestamp = 1000
    # 1m candles: minute 2 hits TP (110.0), minute 8 hits SL (90.0)
    mock_1m = [
        [1060, 99.0, 111.0, 100.0, 110.0, 10],  # Min 1: High 111 >= TP 110
        [1480, 89.0, 102.0, 100.0, 91.0, 10],   # Min 8: Low 89 <= SL 90
    ]
    
    with patch("tpt.engine.evaluator._fetch_1m_candles", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_1m
        res = await _resolve_same_candle_collision(
            client=client,
            symbol="BTC-USD",
            c_time=1000,
            direction="LONG",
            eff_tp=110.0,
            eff_sl=90.0,
            is_be_active=False,
            c_open=100.0,
            c_close=95.0,  # Bearish 15m candle body
        )
        assert res == "WIN"


@pytest.mark.asyncio
async def test_resolve_same_candle_collision_long_sl_first():
    """Verify that when 1m candles show SL hit at minute 1 before TP, status is LOSS/BREAK_EVEN."""
    client = AsyncMock(spec=httpx.AsyncClient)
    
    # 1m candles: minute 1 hits SL (88.0), minute 5 hits TP (112.0)
    mock_1m = [
        [1000, 88.0, 101.0, 100.0, 90.0, 10],   # Min 0: Low 88 <= SL 90
        [1300, 99.0, 112.0, 100.0, 110.0, 10],  # Min 5: High 112 >= TP 110
    ]
    
    with patch("tpt.engine.evaluator._fetch_1m_candles", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_1m
        res = await _resolve_same_candle_collision(
            client=client,
            symbol="BTC-USD",
            c_time=1000,
            direction="LONG",
            eff_tp=110.0,
            eff_sl=90.0,
            is_be_active=False,
            c_open=100.0,
            c_close=105.0,  # Bullish 15m candle body
        )
        assert res == "LOSS"


@pytest.mark.asyncio
async def test_resolve_same_candle_collision_fallback():
    """Verify fallback to candle body color when 1m sub-candle fetch fails."""
    client = AsyncMock(spec=httpx.AsyncClient)
    
    with patch("tpt.engine.evaluator._fetch_1m_candles", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = []
        res = await _resolve_same_candle_collision(
            client=client,
            symbol="BTC-USD",
            c_time=1000,
            direction="LONG",
            eff_tp=110.0,
            eff_sl=90.0,
            is_be_active=False,
            c_open=100.0,
            c_close=105.0,  # Bullish body -> WIN fallback
        )
        assert res == "WIN"
