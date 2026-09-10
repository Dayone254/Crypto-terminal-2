import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

class UIPublisher:
    """Centralized Fast JSON broadcaster feeding Next.js dashboards."""
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"UI Stream Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"UI Stream Client isolated. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict[str, Any]):
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except WebSocketDisconnect:
                dead_connections.append(connection)
            except Exception as e:
                logger.error(f"UI Broadcast mapping dropped: {e}")
                dead_connections.append(connection)
                
        for dc in dead_connections:
            self.disconnect(dc)

# Global publisher block
ui_stream = UIPublisher()
