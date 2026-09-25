"""Unit tests for FastAPI REST API endpoints."""
import httpx
import pytest

from tpt.api.main import app
from tpt.db.connection import init_db


@pytest.mark.asyncio
async def test_health_check_endpoint() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_watchlist_rest_endpoints() -> None:
    await init_db()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Pin symbol
        resp_pin = await client.post("/api/v1/watchlist/HYPE-USD")
        assert resp_pin.status_code == 200
        assert resp_pin.json()["on_watchlist"] is True

        # 2. List watchlist
        resp_list = await client.get("/api/v1/watchlist")
        assert resp_list.status_code == 200
        items = resp_list.json()
        assert any(i["product_id"] == "HYPE-USD" for i in items)

        # 3. Unpin symbol
        resp_unpin = await client.delete("/api/v1/watchlist/HYPE-USD")
        assert resp_unpin.status_code == 200
        assert resp_unpin.json()["on_watchlist"] is False


@pytest.mark.asyncio
async def test_options_websocket_route_registration() -> None:
    routes = [r.path for r in app.routes]
    assert "/api/v1/ws/options/{product_id}" in routes

