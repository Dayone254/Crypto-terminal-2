import asyncio
import json
import logging
import os
from collections import defaultdict
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", None)

class RedisEventBus:
    """
    High-speed Pub/Sub Event Bus.
    Supports Redis backend when available (REDIS_URL), with an auto-fallback
    to an in-memory asyncio Pub/Sub queue system for sub-millisecond local broadcasting.
    """

    def __init__(self):
        self.subscribers: dict[str, set[Callable[[dict[str, Any]], None]]] = defaultdict(set)
        self.async_subscribers: dict[str, set[Callable[[dict[str, Any]], Any]]] = defaultdict(set)
        self._redis = None

    async def connect(self):
        """Initializes Redis connection if configured."""
        if REDIS_URL:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(REDIS_URL)
                logger.info(f"Connected to Redis Pub/Sub at {REDIS_URL}")
            except Exception as e:
                logger.warning(f"Redis connection failed ({e}). Using in-memory EventBus fallback.")
        else:
            logger.info("Using high-performance In-Memory EventBus Pub/Sub.")

    def subscribe(self, channel: str, callback: Callable[[dict[str, Any]], None]):
        """Subscribes a synchronous callback to a channel."""
        self.subscribers[channel].add(callback)

    def subscribe_async(self, channel: str, callback: Callable[[dict[str, Any]], Any]):
        """Subscribes an async callback/queue listener to a channel."""
        self.async_subscribers[channel].add(callback)

    def unsubscribe(self, channel: str, callback: Any):
        """Unsubscribes a listener from a channel."""
        self.subscribers[channel].discard(callback)
        self.async_subscribers[channel].discard(callback)

    async def publish(self, channel: str, payload: dict[str, Any]):
        """Publishes a message to all active channel subscribers."""
        if self._redis:
            try:
                await self._redis.publish(channel, json.dumps(payload))
            except Exception as e:
                logger.error(f"Redis publish error on {channel}: {e}")

        # Local in-memory dispatch
        for cb in list(self.subscribers.get(channel, [])):
            try:
                cb(payload)
            except Exception as e:
                logger.error(f"Error in sync pub/sub callback: {e}")

        for async_cb in list(self.async_subscribers.get(channel, [])):
            try:
                await async_cb(payload)
            except Exception as e:
                logger.error(f"Error in async pub/sub callback: {e}")

event_bus = RedisEventBus()
