"""Build the Telegram application and register handlers."""

from collections.abc import Callable, Coroutine
from typing import Any

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.bot.handlers import callbacks, commands, folders, messages
from app.bot.middleware import guarded
from app.services.container import Container


def _open(
    slug: str,
) -> Callable[[Update, ContextTypes.DEFAULT_TYPE], Coroutine[Any, Any, None]]:
    async def _handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await folders.show(update, context, slug)

    return _handler


_COMMANDS = {
    "start": commands.start,
    "signup": commands.signup,
    "help": commands.help_command,
    "brief": commands.brief,
    "wrapup": commands.wrapup,
    "important": commands.important,
    "unread": commands.unread,
    "tasks": commands.tasks,
    "deadlines": commands.deadlines,
    "followups": commands.followups,
    "calendar": commands.calendar,
    "search": commands.search,
    "suggest": commands.suggest,
    "mail": commands.mail,
    "compose": commands.mail,
    "history": commands.history,
    "preferences": commands.preferences,
    "categories": commands.categories,
    "pause": commands.pause,
    "resume": commands.resume,
    "status": commands.status,
    "errors": commands.errors,
    "folders": folders.menu,
    "menu": folders.menu,
    "meets": _open("meets"),
    "jobs": _open("jobs"),
    "hackathons": _open("hackathons"),
    "otps": _open("otps"),
    "spam": _open("spam"),
    "waiting": _open("waiting"),
    "newsletters": _open("newsletters"),
    "events": _open("events"),
    "scholarships": _open("scholarships"),
    "opportunities": _open("opportunities"),
    "bills": _open("bills"),
    "orders": _open("orders"),
    "travel": _open("travel"),
    "finance": _open("finance"),
    "academics": _open("academics"),
    "filtered": _open("filtered"),
    "vip": _open("vip"),
    "saved": _open("saved"),
    "archive": _open("archive"),
    "focus": commands.focus,
    "templates": commands.templates,
    "interests": commands.interests,
    "done": commands.done,
    "snooze": commands.snooze,
}


def build_application(container: Container) -> Application[Any, Any, Any, Any, Any, Any]:
    """Create the Telegram application and attach the container.

    Args:
        container: Wired services.

    Returns:
        Application that has not been initialized yet.
    """
    token = container.settings.telegram_bot_token or "0:check"
    application = Application.builder().token(token).build()
    application.bot_data["container"] = container
    for name, handler in _COMMANDS.items():
        application.add_handler(CommandHandler(name, guarded(handler)))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, guarded(messages.on_text))
    )
    application.add_handler(CallbackQueryHandler(guarded(callbacks.on_callback)))
    application.add_error_handler(commands.report_error)
    return application
