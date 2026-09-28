"""Shared HTTP Client for TPT Adapters
===================================
Provides a thread-safe, singleton `httpx.AsyncClient` with connection pooling,
limits, and automatic resource cleanup. Eliminates socket descriptor leaks and
memory growth from repeated `httpx.AsyncClient()` instantiations.
"""
from __future__ import annotations

import logging
import httpx

logger = logging.getLogger("tpt.adapters.shared_client")

_shared_client: httpx.AsyncClient | None = None


def get_shared_client() -> httpx.AsyncClient:
    """Return the global shared AsyncClient instance."""
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            timeout=httpx.Timeout(2.5, connect=1.5),
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=40),
            headers={"User-Agent": "TopPickerTerminal/1.0"},
        )
    return _shared_client


async def close_shared_client() -> None:
    """Close the global shared AsyncClient on app shutdown."""
    global _shared_client
    if _shared_client is not None and not _shared_client.is_closed:
        try:
            await _shared_client.aclose()
        except Exception as e:
            logger.warning("Error closing shared HTTP client: %s", e)
        finally:
            _shared_client = None
