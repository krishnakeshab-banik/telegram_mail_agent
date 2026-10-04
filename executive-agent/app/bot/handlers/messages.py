"""Free-text handler. Edits take priority, then the intent router."""

from telegram import Update
from telegram.ext import ContextTypes

from app.bot import formatters, keyboards
from app.bot.handlers import commands
from app.bot.middleware import container_from, reply_html, require_user_id
from app.exceptions import ExecutiveAgentError
from app.services.query_service import QueryResult


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle a plain message from the owner.

    Args:
        update: Telegram update.
        context: Handler context.
    """
    message = update.effective_message
    if message is None or not message.text:
        return
    services = container_from(context)
    user_id = require_user_id(update)
    try:
        preview = await services.replies.apply_pending_edit(user_id, message.text)
        if preview is not None:
            await reply_html(
                update,
                formatters.draft_preview(preview),
                keyboards.draft_actions(preview.approval_id),
            )
            return
        prefs = await services.preferences.get()
        edited = await services.calendar.apply_edit(
            user_id, message.text, prefs.timezone, prefs.reminder_leads
        )
        if edited is not None:
            approval_id, event_id, title, when, warning = edited
            await reply_html(
                update,
                formatters.event_confirmation(title, when, warning),
                keyboards.event_actions(approval_id, event_id),
            )
            return
        if await commands.continue_compose(update, context, message.text):
            return
        folder_reply = await _folder_conversation(services, message.text)
        if folder_reply:
            await reply_html(update, formatters.plain(folder_reply))
            return
        if message.text.lower().startswith("reply "):
            variants = services.suggestions.variants(
                sender_name="there",
                subject="your note",
                instruction=message.text,
            )
            warning = ""
            if variants:
                warning = services.suggestions.preview(
                    to="recipient",
                    subject="your note",
                    body=variants[0].body,
                    has_attachment=False,
                    known_contact=True,
                ).warning
            await reply_html(
                update,
                formatters.reply_choices(
                    [(item.label, item.body) for item in variants],
                    warning,
                ),
            )
            return
        saved = await _maybe_save_template(services, message.text)
        if saved:
            await reply_html(update, formatters.plain(saved))
            return
        if await commands.open_compose(update, context, message.text, explicit=False):
            return
        result = await services.queries.handle(user_id, message.text)
        await _present(update, context, result)
    except ExecutiveAgentError as exc:
        await reply_html(update, formatters.plain(str(exc)))


async def _folder_conversation(services: object, text: str) -> str:
    import json

    from app.services.container import Container
    from app.services.folder_service import parse_folder_request

    if not isinstance(services, Container):
        return ""
    pending = await services.preferences.extra("pending_folder")
    lowered = text.strip().lower()
    if pending and lowered in {"yes", "confirm"}:
        payload = json.loads(pending)
        name = str(payload.get("name", "Custom"))
        keywords = [str(item) for item in payload.get("keywords", [])]
        slug = await services.folders.create_custom(name, keywords)
        await services.preferences.set_extra("pending_folder", "")
        shown = ", ".join(keywords) or "no keywords"
        return f"Saved folder {slug}. It matches: {shown}. Gmail is unchanged."
    if pending and lowered in {"no", "cancel"}:
        await services.preferences.set_extra("pending_folder", "")
        return "Folder not saved."
    request = parse_folder_request(text)
    if request is None:
        return ""
    name, keywords = request
    await services.preferences.set_extra(
        "pending_folder",
        json.dumps({"name": name, "keywords": keywords}),
    )
    shown = ", ".join(keywords) or "no keywords"
    return f"I'll file mail containing: {shown}. Reply yes to save folder {name}."


async def _maybe_save_template(services: object, text: str) -> str:
    from app.services.container import Container

    if not isinstance(services, Container):
        return ""
    lowered = text.strip().lower()
    if not lowered.startswith("save template "):
        return ""
    rest = text.strip()[14:]
    if "::" not in rest:
        return ""
    name, body = rest.split("::", 1)
    if not name.strip() or not body.strip():
        return ""
    stored = await services.templates.save(name.strip(), body.strip())
    return f"Saved template {stored}."


async def _present(update: Update, context: ContextTypes.DEFAULT_TYPE, result: QueryResult) -> None:
    services = container_from(context)
    kind = result.kind
    if kind == "digest":
        await reply_html(update, formatters.digest(await services.briefing.morning()))
        return
    if kind == "wrapup":
        await reply_html(update, formatters.digest(await services.briefing.wrapup()))
        return
    if kind == "calendar":
        context.args = [result.text or "today"]
        await commands.calendar(update, context)
        return
    if kind == "draft" and result.email_id is not None:
        preview = await services.replies.create_preview(
            result.email_id,
            require_user_id(update),
            tone=result.tone,
        )
        await reply_html(
            update, formatters.draft_preview(preview), keyboards.draft_actions(preview.approval_id)
        )
        return
    await reply_html(update, formatters.plain(result.text))
