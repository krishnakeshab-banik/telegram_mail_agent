"""Folder commands and the buttons on those views."""

import asyncio

from telegram import Update
from telegram.ext import ContextTypes

from app.bot import formatters, keyboards
from app.bot.keyboards import folder_keyboards
from app.bot.middleware import container_from, reply_html, require_user_id
from app.db.base import session_scope
from app.db.repositories.email_repository import EmailRepository
from app.services.opportunity_service import field_list

_PENDING_DELETES: set[asyncio.Task[None]] = set()


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show every folder and its active count."""
    counts = await container_from(context).folders.counts()
    rows = [(item.title, item.count) for item in counts]
    markup = folder_keyboards.folder_menu_keyboard(
        [(item.slug, item.title, item.count) for item in counts]
    )
    await reply_html(update, formatters.folder_menu(rows), markup)


async def show(update: Update, context: ContextTypes.DEFAULT_TYPE, slug: str) -> None:
    """Show one page of a folder."""
    query = " ".join(context.args or [])
    await _render_page(update, context, slug, 0, query)


async def on_page(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    """Open a folder page from a button."""
    slug = parts[0] if parts else "important"
    page = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    await _render_page(update, context, slug, page, "")


async def on_status(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    """Move an opportunity along its pipeline. This does not send mail."""
    if len(parts) < 2 or not parts[0].isdigit():
        return
    title = await container_from(context).folders.set_status(int(parts[0]), parts[1])
    text = f"{title} is now {parts[1]}." if title else "That item is no longer available."
    await reply_html(update, formatters.plain(text))


async def on_reveal(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    """Show a one-time code, then delete that Telegram message."""
    if not parts or not parts[0].isdigit():
        return
    code, seconds = await container_from(context).otp.reveal(int(parts[0]))
    chat = update.effective_chat
    if not code or chat is None:
        await reply_html(update, formatters.plain("No code is stored for that mail."))
        return
    sent = await context.bot.send_message(
        chat.id,
        f"Code {code}\nThis message deletes in {seconds} seconds.",
    )

    async def _delete() -> None:
        await asyncio.sleep(seconds)
        try:
            await context.bot.delete_message(chat.id, sent.message_id)
        except Exception:
            return

    task = asyncio.create_task(_delete())
    _PENDING_DELETES.add(task)
    task.add_done_callback(_PENDING_DELETES.discard)


async def on_variant(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    """Preview one suggested reply. Send stays behind the approval button."""
    await _stage_choice(update, context, parts, quick=False)


async def on_quick(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    """Preview a one-tap reply. Nothing is sent until Send."""
    await _stage_choice(update, context, parts, quick=True)


async def _render_page(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    slug: str,
    page: int,
    query: str,
) -> None:
    cards = await container_from(context).folders.page(slug, page, query)
    title = slug.replace("_", " ").title()
    fields = field_list(slug)
    if fields:
        title = f"{title} · {', '.join(fields[:4])}"
    rendered = [(card.title, card.sender, f"{card.detail} · {card.status}") for card in cards]
    markup = folder_keyboards.folder_page_keyboard(slug, page, cards)
    await reply_html(update, formatters.folder_cards(title, rendered), markup)


async def _stage_choice(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    parts: list[str],
    *,
    quick: bool,
) -> None:
    if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return
    services = container_from(context)
    email_id = int(parts[0])
    index = int(parts[1])
    async with session_scope(services.sessions) as session:
        message = await EmailRepository(session).get(email_id)
    if message is None:
        await reply_html(update, formatters.plain("That email is no longer stored."))
        return
    if quick:
        choices = services.suggestions.chips()
    else:
        choices = services.suggestions.variants(
            sender_name=message.sender_name or message.sender_email,
            subject=message.subject,
        )
    if index >= len(choices):
        return
    chosen = choices[index]
    known = await services.contacts.get(message.sender_email)
    extra = message.to_recipients.count(",") if message.to_recipients else 0
    check = services.suggestions.preview(
        to=message.sender_email,
        subject=message.subject,
        body=chosen.body,
        has_attachment=message.has_attachments,
        cc_count=extra,
        known_contact=known is not None,
    )
    preview = await services.replies.stage_body(email_id, require_user_id(update), chosen.body)
    await reply_html(
        update,
        formatters.draft_preview(preview, warning=check.warning),
        keyboards.draft_actions(preview.approval_id),
    )
