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

from app.bot.catalog import COMMANDS
from app.bot.handlers import callbacks, commands, folders, messages
from app.bot.middleware import guarded
from app.services.container import Container


def _open(
    slug: str,
) -> Callable[[Update, ContextTypes.DEFAULT_TYPE], Coroutine[Any, Any, None]]:
    async def _handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await folders.show(update, context, slug)

    return _handler


def _handlers() -> dict[str, Callable[[Update, ContextTypes.DEFAULT_TYPE], Coroutine[Any, Any, None]]]:
    return {
        "start": commands.start,
        "signup": commands.signup,
        "help": commands.help_command,
        "brief": commands.brief,
        "wrapup": commands.wrapup,
        "important": commands.important,
        "unread": commands.unread,
        "tasks": commands.tasks,
        "deadlines": commands.deadlines,
        "waiting": commands.waiting,
        "calendar": commands.calendar,
        "search": commands.search,
        "suggest": commands.suggest,
        "mail": commands.mail,
        "history": commands.history,
        "settings": commands.settings,
        "pause": commands.pause,
        "resume": commands.resume,
        "status": commands.status,
        "errors": commands.errors,
        "folders": folders.menu,
        "focus": commands.focus,
        "templates": commands.templates,
        "interests": commands.interests,
        "done": commands.done,
        "snooze": commands.snooze,
        "today": commands.today,
        "meet": commands.meet,
        "privacy": commands.privacy,
        "disconnect": commands.disconnect,
        "deleteme": commands.delete_me,
        "admin": commands.admin,
    }


def _handler_for(
    key: str,
) -> Callable[[Update, ContextTypes.DEFAULT_TYPE], Coroutine[Any, Any, None]]:
    if key.startswith("folder:"):
        return _open(key.split(":", 1)[1])
    return _handlers()[key]


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
    for spec in COMMANDS:
        application.add_handler(CommandHandler(spec.name, guarded(_handler_for(spec.handler))))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, guarded(messages.on_text))
    )
    application.add_handler(CallbackQueryHandler(guarded(callbacks.on_callback)))
    application.add_error_handler(commands.report_error)
    return application
