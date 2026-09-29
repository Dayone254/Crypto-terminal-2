"""
Gamma regime alerting — Telegram notifications for CONFIRMED regime flips.

Fires only for flips the tracker has confirmed (held for the full window) and
respects a per-underlying+direction cooldown so a whipsawing flip line cannot
spam the chat. Silently no-ops when Telegram is not configured.
"""
from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

_COOLDOWN_SECONDS = 3600.0
_LAST_SENT: dict[str, float] = {}


async def fire_gamma_flip_alert(underlying: str, flip: dict) -> None:
    """flip: {ts, from, to, spot} — a tracker-confirmed regime transition."""
    direction = str(flip.get("to", ""))
    key = f"{underlying}:{direction}"
    now = time.time()
    if now - _LAST_SENT.get(key, 0.0) < _COOLDOWN_SECONDS:
        logger.debug("Gamma flip alert cooldown active for %s", key)
        return

    emoji = "🟢" if "LONG" in direction else "🔴"
    human = (
        "LONG GAMMA — dealers dampening volatility"
        if "LONG" in direction
        else "SHORT GAMMA — dealers amplifying moves"
    )
    spot = flip.get("spot") or 0.0
    spot_line = f"`{underlying}` @ `${spot:,.2f}`" if spot > 0 else f"`{underlying}`"

    message = (
        f"{emoji} *GAMMA REGIME FLIP* — `{underlying}`\n"
        f"{flip.get('from', '?')} → *{direction}*\n"
        f"{spot_line}\n"
        f"{human}\n"
        f"_Top Picker Terminal · Gamma Engine_"
    )

    try:
        from tpt.alerts.telegram import send_raw_alert

        sent = await send_raw_alert(message)
        if sent:
            _LAST_SENT[key] = now
            logger.info("Gamma flip alert sent for %s → %s", underlying, direction)
    except Exception as exc:
        logger.warning("Gamma flip alert failed for %s: %s", underlying, exc)
