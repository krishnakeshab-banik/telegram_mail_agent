"""Allowlist and pause checks. Everyone else is ignored."""

from collections.abc import Callable, Coroutine
from typing import Any

from telegram import Message, Update
from telegram.ext import ContextTypes

from app.services.container import Container

Handler = Callable[[Update, ContextTypes.DEFAULT_TYPE], Coroutine[Any, Any, None]]
_OPEN_WHEN_PAUSED = {"start", "help", "status", "resume", "pause", "signup"}
_PUBLIC_COMMANDS = {"start", "help", "signup"}


def container_from(context: ContextTypes.DEFAULT_TYPE) -> Container:
    """Return the dependency container stored on the application.

    Args:
        context: Handler context.

    Returns:
        Wired container.
    """
    stored = context.application.bot_data["container"]
    if not isinstance(stored, Container):
        raise RuntimeError("The bot container is not configured.")
    return stored


def guarded(handler: Handler) -> Handler:
    """Ignore strangers and stop work while the kill switch is on.

    Args:
        handler: Command, message, or callback handler.

    Returns:
        Wrapped handler.
    """

    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await _allowed(update, context):
            return
        await handler(update, context)

    return wrapped


async def _allowed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    services = container_from(context)
    if user is None:
        return False
    command = _command_name(update)
    known = user.id in services.settings.allowed_user_ids
    if not known:
        known = await services.signups.is_member(user.id)
    if not known and command not in _PUBLIC_COMMANDS:
        message = update.effective_message
        if message is not None:
            await message.reply_text(
                "Send /signup to connect Gmail. I only sync accounts that sign up."
            )
        return False
    if update.effective_chat is not None:
        await services.preferences.remember_chat(update.effective_chat.id)
    if not await services.preferences.is_paused():
        return True
    command = _command_name(update)
    if command in _OPEN_WHEN_PAUSED:
        return True
    if update.callback_query is not None:
        await update.callback_query.answer()
    message = update.effective_message
    if message is not None:
        await message.reply_text("Paused. Send /resume to continue.")
    return False


def _command_name(update: Update) -> str:
    message = update.effective_message
    text = message.text if message and message.text else ""
    if not text.startswith("/"):
        return ""
    return text.split()[0].split("@", 1)[0][1:].lower()


def callback_parts(data: str) -> tuple[str, list[str]]:
    """Split callback data into a prefix and arguments.

    Args:
        data: Raw callback data.

    Returns:
        Prefix and remaining segments.
    """
    pieces = data.split(":")
    return pieces[0], pieces[1:]


def require_user_id(update: Update) -> int:
    """Return the allowlisted user id already checked by the guard.

    Args:
        update: Incoming update.

    Returns:
        Telegram user id.
    """
    user = update.effective_user
    if user is None:
        raise RuntimeError("Update has no user.")
    return user.id


async def reply_html(update: Update, text: str, markup: Any = None) -> None:
    """Send an HTML message to the chat that produced the update.

    Args:
        update: Incoming update.
        text: HTML text.
        markup: Optional inline keyboard.
    """
    message: Message | None = update.effective_message
    if message is None and update.callback_query is not None:
        candidate = update.callback_query.message
        if isinstance(candidate, Message):
            message = candidate
    if message is None:
        return
    await message.reply_text(text, parse_mode="HTML", reply_markup=markup)
