"""FastAPI WebSocket route — streams real-time Options Flow & Gamma Engine metrics down to clients."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from tpt.config.settings import settings
from tpt.engine.ws_memory import ws_memory

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/{product_id}")
async def options_flow_stream(websocket: WebSocket, product_id: str, expiry: str = "ALL"):
    """
    Streams live Gamma Engine metrics (GEX distribution, Dealer Greeks, IV skew,
    Call/Put walls, Gamma Flip, and Orderflow Confluence) to connected clients.
    """
    await websocket.accept()
    if not settings.enable_live_ws:
        await websocket.send_json({
            "type": "ws_disabled",
            "error": "live_ws_disabled",
            "message": "Live streaming is disabled (ENABLE_LIVE_WS=false).",
        })
        await websocket.close(code=1000)
        return

    underlying = product_id.split("-")[0].upper()

    logger.info("Options flow stream opened for %s (underlying %s, expiry %s)", product_id, underlying, expiry)

    last_sent_hash: str | None = None

    async def feed_client():
        nonlocal last_sent_hash
        while True:
            try:
                options_data = ws_memory.get_macro_options(underlying) if expiry.upper() == "ALL" else None
                if not options_data:
                    # If not cached yet or expiry filter is active, compute exposure
                    from tpt.engine.options_flow import calculate_macro_gamma_exposure
                    options_data = await calculate_macro_gamma_exposure(underlying, 0.0, expiry_filter=expiry)
                    if options_data and expiry.upper() == "ALL":
                        ws_memory.macro_options_cache[underlying] = options_data

                if options_data:
                    # Send payload frame (include expiry_available so 0DTE state transitions are never suppressed)
                    data_str = (
                        str(options_data.get("spot_price"))
                        + str(options_data.get("total_net_gex_millions"))
                        + str(options_data.get("orderflow", {}).get("confluence_score"))
                        + str(options_data.get("expiry_available"))
                        + expiry
                    )

                    if data_str != last_sent_hash:
                        last_sent_hash = data_str
                        await websocket.send_json(options_data)

                await asyncio.sleep(1.0)
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"Error streaming options flow for {product_id}: {e}")
                break

    feed_task = asyncio.create_task(feed_client())

    try:
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        logger.info("Options flow stream closed for %s", product_id)
    except Exception as e:
        logger.error("Options flow stream error for %s: %s", product_id, e)
    finally:
        feed_task.cancel()
