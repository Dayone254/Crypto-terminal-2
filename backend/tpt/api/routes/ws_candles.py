"""FastAPI WebSocket route — streams real-time price ticks for a given symbol."""
import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from tpt.config.settings import settings
from tpt.engine.ws_candle import stream_ticker

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/{product_id}")
async def candle_tick_stream(websocket: WebSocket, product_id: str):
    """Stream live ticker ticks for NativeChart animation."""
    await websocket.accept()
    if not settings.enable_live_ws:
        # Live streaming is opt-in (ENABLE_LIVE_WS). Signal it explicitly and
        # close, so a blocked WS network path can't become a per-client retry
        # storm. Clients must NOT interpret this frame as ticker data.
        await websocket.send_json({
            "type": "ws_disabled",
            "error": "live_ws_disabled",
            "message": "Live streaming is disabled (ENABLE_LIVE_WS=false).",
        })
        await websocket.close(code=1000)
        return

    logger.info("Tick stream opened for %s", product_id)

    async def feed():
        async for tick in stream_ticker(product_id):
            try:
                await websocket.send_json(tick)
            except (WebSocketDisconnect, Exception):
                return

    feed_task = asyncio.create_task(feed())
    try:
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        logger.info("Tick stream closed for %s", product_id)
    finally:
        feed_task.cancel()
