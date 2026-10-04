"""Publish the bot description and slash-command menu to Telegram."""

from telegram import Bot, BotCommand

from app.bot.catalog import COMMAND_MENU, DESCRIPTION, SHORT_DESCRIPTION
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def publish_bot_profile(bot: Bot) -> None:
    """Set the profile description and the command list shown in Telegram.

    Args:
        bot: Connected Telegram bot.
    """
    await bot.set_my_short_description(SHORT_DESCRIPTION)
    await bot.set_my_description(DESCRIPTION)
    await bot.set_my_commands([BotCommand(name, text) for name, text in COMMAND_MENU])
    logger.info("bot_profile_published", commands=len(COMMAND_MENU))
