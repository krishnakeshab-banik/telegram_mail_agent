"""Allowlist and pause checks. Everyone else is ignored."""

from collections.abc import Callable, Coroutine
from typing import Any

from telegram import Message, Update
from telegram.ext import ContextTypes

from app.db.models.user import User
from app.db.user_context import user_scope
from app.services.container import Container

Handler = Callable[[Update, ContextTypes.DEFAULT_TYPE], Coroutine[Any, Any, None]]
_OPEN_WHEN_PAUSED = {
    "start",
    "help",
    "status",
    "resume",
    "pause",
    "signup",
    "privacy",
    "settings",
    "disconnect",
    "deleteme",
}
_SIGNUP_COMMANDS = {"start", "signup", "privacy", "disconnect", "deleteme"}
_ANON_COMMANDS = {"start", "signup", "privacy"}
_SIGNUP_CALLBACKS = {"agr", "prv", "gol", "tz", "qh", "rm", "dc", "da", "how"}


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
        account = await _resolve_account(update, context)
        command = _command_name(update)
        callback = _callback_prefix(update)
        is_text = _is_plain_text(update)
        allowed = access_allowed(
            has_account=account is not None,
            status="" if account is None else account.status,
            command=command,
            callback=callback,
            is_text=is_text,
        )
        if not allowed:
            if update.callback_query is not None:
                await update.callback_query.answer()
            return
        if account is None:
            await handler(update, context)
            return
        with user_scope(account.id):
            if update.effective_chat is not None:
                await container_from(context).users.remember_chat(
                    account.id, update.effective_chat.id
                )
                if account.id == container_from(context).owner_id:
                    await container_from(context).preferences.remember_chat(
                        update.effective_chat.id
                    )
            if account.status == "active" and not await _pause_allows(update, context):
                return
            await handler(update, context)

    return wrapped


async def _resolve_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> User | None:
    user = update.effective_user
    if user is None:
        return None
    services = container_from(context)
    account = await services.users.by_telegram(user.id)
    if account is not None:
        return account
    if user.id not in services.settings.allowed_user_ids:
        return None
    owner = await services.users.ensure_owner()
    if owner.telegram_user_id == user.id:
        return owner
    return None


def access_allowed(
    *,
    has_account: bool,
    status: str,
    command: str,
    callback: str,
    is_text: bool,
) -> bool:
    """Return whether this update may run. Banned users and strangers get silence."""
    if status == "banned":
        return False
    if not has_account:
        return command in _ANON_COMMANDS or callback in {"agr", "prv", "how", "gol"}
    if status == "pending":
        return command in _SIGNUP_COMMANDS or callback in _SIGNUP_CALLBACKS or is_text
    return True


async def _pause_allows(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    services = container_from(context)
    if not await services.preferences.is_paused():
        return True
    if _command_name(update) in _OPEN_WHEN_PAUSED:
        return True
    message = update.effective_message
    if message is not None and (message.text or "").strip() == "DELETE":
        return True
    if update.callback_query is not None:
        await update.callback_query.answer()
    message = update.effective_message
    if message is not None:
        await message.reply_text("Paused. Send /resume to continue.")
    return False


def _callback_prefix(update: Update) -> str:
    query = update.callback_query
    data = query.data if query is not None and query.data else ""
    return data.split(":", 1)[0]


def _is_plain_text(update: Update) -> bool:
    message = update.effective_message
    text = message.text if message is not None and message.text else ""
    return bool(text) and not text.startswith("/")


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
