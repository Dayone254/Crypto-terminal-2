import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from tpt.engine.l2_multiplexer import stream_multiplexed_l2
from tpt.engine.l2_processor import process_l2_book

logger = logging.getLogger(__name__)

router = APIRouter()

@router.websocket("/{product_id}")
async def l2_orderbook_stream(websocket: WebSocket, product_id: str):
    """
    Streams processed Level 2 Orderbook data down to the client.
    Connects to Binance & Coinbase WS for raw depth, processes imbalance/walls locally,
    and relays frames.
    """
    await websocket.accept()
    logger.info(f"Client connected to L2 stream for {product_id}")
    
    # We create a task to consume from multiplexer
    async def feed_client():
        async for raw_book in stream_multiplexed_l2(product_id):
            processed_data = process_l2_book(raw_book)
            try:
                await websocket.send_json(processed_data)
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"Error sending L2 data to client: {e}")
                break

    feed_task = asyncio.create_task(feed_client())
    
    try:
        # Keep connection open until client disconnects
        while True:
            # We can also receive messages from the client if needed
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        logger.info(f"Client disconnected from L2 stream for {product_id}")
    except Exception as e:
        logger.error(f"L2 stream error for {product_id}: {e}")
    finally:
        feed_task.cancel()
        
