"""
Deribit Real-Time WebSocket Options Streamer
============================================
Connects to the Deribit public WebSocket API and maintains a live, in-memory
options board updated in <100ms — replacing the 15-second REST polling cycle
for Deribit BTC/ETH options.

Architecture:
  - One coroutine per underlying (BTC, ETH)
  - Subscribes to all active *-C and *-P instrument tickers via batch subscription
  - Reconnects with exponential backoff (1s → 60s max)
  - Thread-safe dict for concurrent reads from options_flow.py

Usage:
    Live board is accessed via:
        from tpt.adapters.deribit_ws import get_live_board
        board = get_live_board("BTC")   # returns list[dict] or []

    The board is started via ws_memory.start_options_daemon().
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

logger = logging.getLogger("tpt.adapters.deribit_ws")

# ---------------------------------------------------------------------------
# In-memory live board (underlying → contract_dict → ticker data)
# ---------------------------------------------------------------------------
_LIVE_BOARDS: dict[str, dict[str, dict[str, Any]]] = {}
_LAST_UPDATE:  dict[str, float] = {}
_MAX_STALE_SECONDS = 60.0   # if no update in 60s, consider board stale

# Reconnect backoff
_MIN_BACKOFF = 1.0
_MAX_BACKOFF = 60.0

DERIBIT_WS_URL = "wss://www.deribit.com/ws/api/v2"


def get_live_board(underlying: str) -> list[dict[str, Any]]:
    """
    Return the current live Deribit options board for the given underlying.
    Returns [] if the board is empty or stale (>60s since last update).
    """
    key = underlying.upper()
    last = _LAST_UPDATE.get(key, 0.0)
    if time.time() - last > _MAX_STALE_SECONDS:
        return []
    board_dict = _LIVE_BOARDS.get(key, {})
    return [_to_board_entry(sym, data, underlying) for sym, data in board_dict.items()
            if data.get("_oi_coin", 0) > 0]


def is_live(underlying: str) -> bool:
    """True if the WS board for this underlying was updated within the stale window."""
    return time.time() - _LAST_UPDATE.get(underlying.upper(), 0.0) < _MAX_STALE_SECONDS


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_instrument(inst_name: str) -> tuple[str, float, str] | None:
    """
    Parse Deribit instrument name → (expiry_str, strike, opt_type).
    Format: BTC-27SEP24-65000-C
    """
    parts = inst_name.split("-")
    if len(parts) != 4:
        return None
    try:
        expiry_str = parts[1]
        strike = float(parts[2])
        opt_type = parts[3].upper()
        if opt_type not in ("C", "P"):
            return None
        return expiry_str, strike, opt_type
    except (ValueError, IndexError):
        return None


def _to_board_entry(symbol: str, data: dict, underlying: str) -> dict[str, Any]:
    """Convert live ticker cache entry to the standard options board format."""
    oi_coin = float(data.get("_oi_coin", 0))
    und_px  = float(data.get("underlying_price", 0))
    parsed  = data.get("_parsed")

    fallback_spot = 2600.0 if underlying.upper() == "ETH" else 140.0 if underlying.upper() == "SOL" else 90000.0
    return {
        "venue":              "Deribit",
        "symbol":             symbol,
        "underlying":         underlying,
        "expiry_str":         parsed[0] if parsed else "",
        "strike":             parsed[1] if parsed else 0.0,
        "type":               parsed[2] if parsed else "C",
        "bid_price":          float(data.get("best_bid_price",  0) or 0),
        "ask_price":          float(data.get("best_ask_price",  0) or 0),
        "open_interest":      oi_coin,
        "open_interest_usd":  oi_coin * und_px if und_px > 0 else oi_coin * fallback_spot,
        "volume":             float(data.get("stats", {}).get("volume", 0) or 0),
        "mark_price":         float(data.get("mark_price",       0) or 0),
        "underlying_price":   und_px,
        "implied_volatility": float(data.get("mark_iv",          0) or 0) / 100.0,
    }


# ---------------------------------------------------------------------------
# WebSocket session per underlying
# ---------------------------------------------------------------------------

async def _run_ws_for_underlying(underlying: str) -> None:
    """
    Long-running coroutine: connects to Deribit WS, subscribes to all option
    tickers for *underlying*, and streams updates into _LIVE_BOARDS.
    Reconnects with exponential backoff on any failure.
    """
    try:
        import websockets  # ensure available
    except ImportError:
        logger.error("websockets package not installed — Deribit WS disabled")
        return

    key = underlying.upper()
    _LIVE_BOARDS.setdefault(key, {})
    backoff = _MIN_BACKOFF

    while True:
        try:
            logger.info("Deribit WS: connecting for %s …", underlying)
            async with websockets.connect(
                DERIBIT_WS_URL,
                ping_interval=20,
                ping_timeout=10,
                open_timeout=10,
            ) as ws:
                backoff = _MIN_BACKOFF   # reset on successful connect

                # Step 1: fetch all active option instruments
                await ws.send(json.dumps({
                    "jsonrpc": "2.0", "id": 1,
                    "method": "public/get_instruments",
                    "params": {"currency": key, "kind": "option", "expired": False},
                }))
                resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                instruments = [r["instrument_name"] for r in resp.get("result", [])
                               if r.get("instrument_name")]

                if not instruments:
                    logger.warning("Deribit WS: no instruments for %s, retrying in %ss", underlying, backoff)
                    await asyncio.sleep(backoff)
                    continue

                logger.info("Deribit WS: subscribing to %d %s instruments", len(instruments), underlying)

                # Seed board with parsed metadata
                for inst in instruments:
                    parsed = _parse_instrument(inst)
                    if parsed:
                        _LIVE_BOARDS[key].setdefault(inst, {})["_parsed"] = parsed

                # Step 2: subscribe in chunks of 100 (WS msg size limit)
                channels = [f"ticker.{i}.raw" for i in instruments]
                for chunk_start in range(0, len(channels), 100):
                    chunk = channels[chunk_start:chunk_start + 100]
                    await ws.send(json.dumps({
                        "jsonrpc": "2.0", "id": 2 + chunk_start,
                        "method": "public/subscribe",
                        "params": {"channels": chunk},
                    }))
                    # Small delay between subscription batches to respect rate limits
                    await asyncio.sleep(0.1)

                logger.info("Deribit WS %s: fully subscribed, streaming live tickers", underlying)

                # Step 3: stream
                async for raw_msg in ws:
                    try:
                        msg = json.loads(raw_msg)
                        if msg.get("method") != "subscription":
                            continue
                        params = msg.get("params", {})
                        channel = params.get("channel", "")
                        if not channel.startswith("ticker."):
                            continue
                        data = params.get("data", {})
                        inst_name = data.get("instrument_name", "")
                        if not inst_name:
                            continue

                        # Update live board entry
                        entry = _LIVE_BOARDS[key].get(inst_name, {})
                        entry.update(data)
                        oi_coin = float(data.get("open_interest", entry.get("_oi_coin", 0)) or 0)
                        entry["_oi_coin"] = oi_coin
                        entry.setdefault("_parsed", _parse_instrument(inst_name))
                        _LIVE_BOARDS[key][inst_name] = entry
                        _LAST_UPDATE[key] = time.time()

                    except Exception as parse_err:
                        logger.debug("Deribit WS parse error: %s", parse_err)

        except asyncio.CancelledError:
            logger.info("Deribit WS stream cancelled for %s", underlying)
            return
        except Exception as exc:
            logger.warning("Deribit WS %s disconnected: %s — reconnecting in %.0fs",
                           underlying, exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF)


# ---------------------------------------------------------------------------
# Public launcher (called from ws_memory)
# ---------------------------------------------------------------------------

_WS_TASKS: dict[str, asyncio.Task] = {}


def start_deribit_ws_streams(underlyings: list[str] | None = None) -> None:
    """
    Launch persistent WS stream tasks for each underlying.
    Safe to call multiple times — skips underlyings already running.
    """
    if underlyings is None:
        underlyings = ["BTC", "ETH"]
    for u in underlyings:
        key = u.upper()
        task = _WS_TASKS.get(key)
        if task is None or task.done():
            _WS_TASKS[key] = asyncio.create_task(_run_ws_for_underlying(key))
            logger.info("Deribit WS stream task started for %s", key)
