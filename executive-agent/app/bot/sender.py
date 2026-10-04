"""Telegram delivery used by scheduled jobs."""

from typing import Any

from telegram import Bot

from app.utils.logging import get_logger

logger = get_logger(__name__)


class TelegramSender:
    """Sends HTML messages once the bot has been bound at startup."""

    def __init__(self) -> None:
        """Create a sender that is inert until bind is called."""
        self._bot: Bot | None = None

    def bind(self, bot: Bot) -> None:
        """Attach the running bot.

        Args:
            bot: python-telegram-bot Bot instance.
        """
        self._bot = bot

    async def send_text(self, chat_id: int, text: str, markup: Any = None) -> None:
        """Send one HTML message.

        Args:
            chat_id: Destination chat.
            text: HTML text.
            markup: Optional inline keyboard.
        """
        if self._bot is None:
            logger.warning("telegram_sender_unbound")
            return
        await self._bot.send_message(
            chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=markup
        )
