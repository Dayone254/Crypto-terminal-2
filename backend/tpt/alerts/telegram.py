"""Telegram alert dispatcher — sends setup notifications to a configured chat."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def send_setup_alert(
    symbol: str,
    score: float,
    label: str,
    entry: float,
    tp: float,
    sl: float,
) -> None:
    """Fire a Telegram message for a new high-conviction setup.
    
    Silently no-ops if TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID are not configured.
    """
    from tpt.config.settings import settings

    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id

    if not token or not chat_id:
        logger.debug("Telegram not configured — skipping alert for %s", symbol)
        return

    try:
        from telegram import Bot

        # Emoji by label
        emoji_map = {
            "ENTRY_ZONE": "🟢",
            "COILED": "🟡",
            "EARLY": "🔵",
            "WATCH": "⚪",
        }
        emoji = emoji_map.get(label, "⚪")

        # Percent Risk/Reward
        rr_tp = ((tp - entry) / entry * 100) if entry > 0 else 0.0
        rr_sl = ((sl - entry) / entry * 100) if entry > 0 else 0.0

        message = (
            f"{emoji} *\\[{label}\\]* `{symbol}`\n"
            f"📊 Score: *{score:.0f}/100*\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"📥 Entry: `${entry:,.4f}`\n"
            f"🎯 TP:    `${tp:,.4f}`  \\(+{rr_tp:.1f}%\\)\n"
            f"🛡️  SL:    `${sl:,.4f}`  \\({rr_sl:.1f}%\\)\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"_Top Picker Terminal_"
        )

        bot = Bot(token=token)
        await bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode="MarkdownV2",
        )
        logger.info("Telegram alert dispatched for %s [%s]", symbol, label)

    except Exception as exc:
        # Never crash the scanner over an alert failure
        logger.warning("Telegram alert failed for %s: %s", symbol, exc)
