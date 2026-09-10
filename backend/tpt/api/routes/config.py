"""Config API routes."""
from __future__ import annotations

import json
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from tpt.db.connection import get_session
from tpt.db.write_lock import db_write_lock

router = APIRouter()
logger = logging.getLogger(__name__)

# Canonical key under which scoring overrides are stored. The loader accepts
# this and the legacy "components" alias.
_OVERRIDE_KEY = "scoring_weights_override"


class TelegramConfig(BaseModel):
    telegram_bot_token: str
    telegram_chat_id: str


def _sanitize_env_value(value: str) -> str:
    """Reject values that could inject additional .env lines.

    An unauthenticated POST used to write caller-supplied strings straight into
    .env, so a value containing a newline could append arbitrary KEY=VALUE pairs.
    """
    if "\n" in value or "\r" in value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Value must not contain line breaks.",
        )
    return value.strip()


def _validate_weight_map(weights: dict) -> dict[str, float]:
    """Ensure overrides are plain numbers in [0, 1] so scoring can't be broken."""
    if not isinstance(weights, dict):
        raise HTTPException(status_code=400, detail="Weights must be an object.")
    cleaned: dict[str, float] = {}
    for key, value in weights.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise HTTPException(status_code=400, detail=f"Weight '{key}' must be a number.")
        if not 0.0 <= float(value) <= 1.0:
            raise HTTPException(status_code=400, detail=f"Weight '{key}' must be between 0 and 1.")
        cleaned[str(key)] = float(value)
    return cleaned


@router.get("")
async def get_config() -> dict:
    """Return effective config (merged env + yaml + db overrides)."""
    from tpt.config.settings import settings
    return {
        "telegram_configured": bool(settings.telegram_bot_token and settings.telegram_chat_id),
        "telegram_chat_id": settings.telegram_chat_id,
        "ml_scoring_enabled": settings.enable_ml_scoring,
        "auth_required": bool(settings.api_token),
        # Never expose the token itself
    }


@router.get("/scoring")
async def get_scoring_config() -> dict:
    """Return effective scoring configuration (yaml + persisted overrides)."""
    from tpt.config.strategy import load_strategy
    return load_strategy().scoring.model_dump()


@router.patch("/scoring")
async def patch_scoring_config(updates: dict, db=Depends(get_session)) -> dict:
    """Apply partial mapping updates to the scoring config and persist to DB."""
    from tpt.config.strategy import load_strategy
    from tpt.db.models import UserSetting

    # Accept both the canonical and legacy payload shapes.
    incoming = updates.get("component_weights", updates.get("components"))

    async with db_write_lock:
        us = await db.get(UserSetting, _OVERRIDE_KEY)
        current_overrides = json.loads(us.value) if us and us.value else {}
        weight_map = current_overrides.setdefault("component_weights", {})

        if incoming:
            for direction, weights in incoming.items():
                if direction not in ("LONG", "SHORT"):
                    raise HTTPException(status_code=400, detail=f"Unknown direction '{direction}'.")
                weight_map.setdefault(direction, {}).update(_validate_weight_map(weights))

        if us is None:
            us = UserSetting(key=_OVERRIDE_KEY, value=json.dumps(current_overrides))
            db.add(us)
        else:
            us.value = json.dumps(current_overrides)
        await db.commit()

    # Apply immediately in-process; the scanner also re-reads per scan run.
    load_strategy(force_reload=True)
    return {"ok": True, "overrides": current_overrides}


@router.delete("/scoring")
async def reset_scoring_config(db=Depends(get_session)) -> dict:
    """Clear all scoring overrides and restore base YAML defaults."""
    from tpt.config.strategy import load_strategy
    from tpt.db.models import UserSetting

    async with db_write_lock:
        us = await db.get(UserSetting, _OVERRIDE_KEY)
        if us:
            await db.delete(us)
            await db.commit()

    load_strategy(force_reload=True)
    return {"ok": True, "message": "Restored to defaults."}


@router.post("/telegram")
async def configure_telegram(cfg: TelegramConfig) -> dict:
    """Persist Telegram bot token and chat ID to the .env file."""
    from tpt.config.settings import settings

    token = _sanitize_env_value(cfg.telegram_bot_token)
    chat_id = _sanitize_env_value(cfg.telegram_chat_id)

    env_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".env")
    )

    lines: list[str] = []
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            lines = f.readlines()

    keys = {"TELEGRAM_BOT_TOKEN": token, "TELEGRAM_CHAT_ID": chat_id}
    existing_keys: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        matched = False
        for k in keys:
            if line.startswith(f"{k}="):
                new_lines.append(f"{k}={keys[k]}\n")
                existing_keys.add(k)
                matched = True
                break
        if not matched:
            new_lines.append(line)
    for k, v in keys.items():
        if k not in existing_keys:
            new_lines.append(f"{k}={v}\n")

    # Write atomically so a crash can't leave .env truncated.
    tmp_path = f"{env_path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    os.replace(tmp_path, env_path)

    settings.telegram_bot_token = token
    settings.telegram_chat_id = chat_id

    return {"ok": True, "message": "Telegram credentials saved. Will take effect immediately."}


@router.post("/telegram/test")
async def test_telegram() -> dict:
    """Send a test Telegram message to verify configuration."""
    from tpt.config.settings import settings

    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return {"ok": False, "message": "Telegram not configured."}

    try:
        from telegram import Bot

        bot = Bot(token=settings.telegram_bot_token)
        await bot.send_message(
            chat_id=settings.telegram_chat_id,
            text="✅ *Top Picker Terminal* connected successfully\\! You will now receive setup alerts here\\.",
            parse_mode="MarkdownV2",
        )
        return {"ok": True, "message": "Test message sent!"}
    except Exception as exc:
        # Log the detail, return a generic message — never echo upstream errors.
        logger.warning("Telegram test failed: %s", exc)
        return {"ok": False, "message": "Telegram test failed. Check the server logs for details."}
