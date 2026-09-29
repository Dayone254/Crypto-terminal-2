"""Telegram alert dispatcher — sends setup notifications to a configured chat."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def send_raw_alert(markdown_text: str) -> bool:
    """Send a pre-formatted MarkdownV2 message. Returns True when delivered.

    Used by non-setup alerters (gamma regime flips etc.) that build their own
    message body. No-ops (returns False) when Telegram is not configured and
    swallows transport errors — alerting must never break the caller's loop.
    """
    from tpt.config.settings import settings

    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id
    if not token or not chat_id:
        logger.debug("Telegram not configured — skipping raw alert")
        return False
    try:
        from telegram import Bot

        bot = Bot(token=token)
        await bot.send_message(
            chat_id=chat_id,
            text=markdown_text,
            parse_mode="MarkdownV2",
        )
        return True
    except Exception as exc:
        logger.warning("Telegram raw alert failed: %s", exc)
        return False


async def send_setup_alert(
    symbol: str,
    score: float,
    label: str,
    entry: float,
    tp: float | None = None,
    sl: float | None = None,
    bypass_quiet_hours: bool = False,
) -> None:
    """Fire a Telegram message for a new high-conviction setup.

    Silently no-ops if TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID are not configured.
    Respects user quiet hours unless bypass_quiet_hours is True.

    ``tp``/``sl`` are optional: when the caller has no real levels (e.g. an alert
    without a ladder snapshot) they are simply omitted from the message instead
    of the caller having to fabricate plausible-looking numbers.
    """
    from tpt.config.settings import settings
    from tpt.config.strategy import load_strategy
    from tpt.alerting.quiet_hours import should_deliver
    from datetime import UTC, datetime

    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id

    if not token or not chat_id:
        logger.debug("Telegram not configured — skipping alert for %s", symbol)
        return

    if not bypass_quiet_hours:
        cfg = load_strategy().alerts
        now = datetime.now(UTC)
        if not should_deliver(None, now, cfg.quiet_hours_start, cfg.quiet_hours_end, cfg.timezone):
            logger.info("Quiet hours active — suppressing setup alert for %s", symbol)
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

        # Percent Risk/Reward — only when real levels were supplied.
        rr_tp = ((tp - entry) / entry * 100) if (tp is not None and entry > 0) else 0.0
        rr_sl = ((sl - entry) / entry * 100) if (sl is not None and entry > 0) else 0.0

        lines = [
            f"{emoji} *\\[{label}\\]* `{symbol}`\n",
            f"📊 Score: *{score:.0f}/100*\n",
            f"━━━━━━━━━━━━━━━━\n",
            f"📥 Entry: `${entry:,.4f}`\n",
        ]
        if tp is not None:
            lines.append(f"🎯 TP:    `${tp:,.4f}`  \\(+{rr_tp:.1f}%\\)\n")
        if sl is not None:
            lines.append(f"🛡️  SL:    `${sl:,.4f}`  \\({rr_sl:.1f}%\\)\n")
        lines.extend([
            f"━━━━━━━━━━━━━━━━\n",
            f"_Top Picker Terminal_",
        ])
        message = "".join(lines)

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
