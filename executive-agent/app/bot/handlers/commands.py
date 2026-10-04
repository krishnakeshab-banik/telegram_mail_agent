"""Telegram command handlers. Each handler calls one service and formats the result."""

from datetime import timedelta

from telegram import Update
from telegram.ext import ContextTypes

from app.bot import formatters, keyboards
from app.bot.middleware import container_from, reply_html, require_user_id
from app.exceptions import ExecutiveAgentError, RecordNotFoundError
from app.utils.logging import get_logger
from app.utils.security import redact
from app.utils.time import format_local, to_local, utcnow

logger = get_logger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Register the chat and explain the agent."""
    await reply_html(update, formatters.welcome())


async def signup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Connect the sender's Google account. The browser opens on this computer."""
    chat = update.effective_chat
    if chat is None:
        return
    await reply_html(
        update,
        formatters.plain(
            "Opening Google sign-in on the computer running this agent. "
            "Choose the Gmail account to sync."
        ),
    )
    try:
        email = await container_from(context).signups.connect(require_user_id(update), chat.id)
    except ExecutiveAgentError as exc:
        await reply_html(update, formatters.plain(str(exc)))
        return
    await reply_html(
        update,
        formatters.plain(f"Connected {email}. I will pull the last 7 days on the next sync."),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the command reference."""
    del context
    await reply_html(update, formatters.help_text())


async def brief(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the morning briefing."""
    digest = await container_from(context).briefing.morning()
    await reply_html(update, formatters.digest(digest))


async def wrapup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the evening wrap-up."""
    digest = await container_from(context).briefing.wrapup()
    await reply_html(update, formatters.digest(digest))


async def important(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List important mail."""
    lines = await container_from(context).inbox.important_lines()
    await reply_html(update, formatters.bullet_list("Important", lines))


async def unread(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List unread mail."""
    lines = await container_from(context).inbox.unread_lines()
    await reply_html(update, formatters.bullet_list("Unread", lines))


async def tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List open tasks that survived the quality filter."""
    rows = await container_from(context).tasks.list_open()
    lines = [f"t{task.id} {task.title}" for task in rows]
    await reply_html(update, formatters.bullet_list("Tasks", lines))


async def deadlines(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List deadlines, marking past ones as overdue."""
    from app.utils.time import describe_due, utcnow

    rows = await container_from(context).tasks.list_deadlines()
    now = utcnow()
    lines = []
    for item in rows:
        when = describe_due(item.due_at, now) if item.due_at else "no date"
        bucket = "Missed or overdue" if when == "overdue" else "Upcoming"
        lines.append(f"d{item.id} [{bucket}] {item.title} — {when}")
    await reply_html(update, formatters.bullet_list("Deadlines", lines))


async def followups(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List pending follow-ups."""
    rows = await container_from(context).followups.list_open()
    lines = [
        f"f{item.id} {item.direction}: {item.subject or item.counterpart_email}" for item in rows
    ]
    await reply_html(update, formatters.bullet_list("Follow-ups", lines))


async def calendar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show today's events, or the week when the argument is week."""
    services = container_from(context)
    prefs = await services.preferences.get()
    start = to_local(utcnow(), prefs.timezone)
    window = context.args[0].lower() if context.args else "today"
    end = (
        start + timedelta(days=7)
        if window == "week"
        else start.replace(hour=23, minute=59, second=0)
    )
    events = await services.calendar.list_window(start, end)
    lines = [f"{format_local(item.start, prefs.timezone)} {item.title}" for item in events]
    await reply_html(update, formatters.bullet_list("Calendar", lines))


async def mail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Structure a new email and wait for Send. Nothing is sent here."""
    text = " ".join(context.args or [])
    await open_compose(update, context, text, explicit=True)


async def continue_compose(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
    """Use the next owner message as the body of a mail that already has an address."""
    services = container_from(context)
    recipient = await services.preferences.extra("pending_compose")
    if not recipient:
        return False
    if text.strip().lower() in {"no", "cancel"}:
        await services.preferences.set_extra("pending_compose", "")
        await reply_html(update, formatters.plain("New mail cancelled. Nothing was sent."))
        return True
    await services.preferences.set_extra("pending_compose", "")
    await open_compose(update, context, f"email {recipient} {text}", explicit=True)
    return True


async def open_compose(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    *,
    explicit: bool,
) -> bool:
    """Draft a new email when the owner gave an address and a note."""
    from app.services.compose_service import parse_compose, structure_mail

    request = parse_compose(text, explicit=explicit)
    if request is None:
        if not explicit:
            return False
        await reply_html(
            update,
            formatters.plain("Usage: /mail person@example.com what you want to tell them"),
        )
        return True
    services = container_from(context)
    if not request.message:
        await services.preferences.set_extra("pending_compose", request.recipient)
        await reply_html(
            update,
            formatters.plain(
                f"What should I tell {request.recipient}? "
                "Send the next message and I will show a draft."
            ),
        )
        return True
    prefs = await services.preferences.get()
    subject, body = structure_mail(request.message, tone=prefs.tone)
    known = await services.contacts.get(request.recipient)
    warning = services.suggestions.preview(
        to=request.recipient,
        subject=subject,
        body=body,
        has_attachment=False,
        known_contact=known is not None,
    ).warning
    preview = await services.replies.stage_compose(
        recipient=request.recipient,
        subject=subject,
        body=body,
        instruction=request.message,
        tone=prefs.tone,
        telegram_user_id=require_user_id(update),
    )
    await reply_html(
        update,
        formatters.draft_preview(preview, warning=warning),
        keyboards.draft_actions(preview.approval_id),
    )
    return True


async def suggest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show reply suggestions. Nothing is sent."""
    instruction = " ".join(context.args or [])
    service = container_from(context).suggestions
    variants = service.variants(sender_name="there", subject="your note", instruction=instruction)
    warning = ""
    if variants:
        warning = service.preview(
            to="recipient",
            subject="your note",
            body=variants[0].body,
            has_attachment=False,
            known_contact=True,
        ).warning
    await reply_html(
        update,
        formatters.reply_choices([(item.label, item.body) for item in variants], warning),
    )


async def focus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Silence ordinary alerts for a few hours. Critical and phishing still come through."""
    raw = (context.args[0].lower() if context.args else "2h").strip()
    services = container_from(context)
    if raw in {"off", "stop"}:
        await services.preferences.set_extra("focus_until", "")
        await reply_html(update, formatters.plain("Focus mode is off."))
        return
    hours = 2
    if raw.endswith("h") and raw[:-1].isdigit():
        hours = max(1, int(raw[:-1]))
    elif raw.isdigit():
        hours = max(1, int(raw))
    until = utcnow() + timedelta(hours=hours)
    await services.preferences.set_extra("focus_until", until.isoformat())
    await reply_html(
        update,
        formatters.plain(
            f"Focus for {hours} hours. Only critical items and phishing alerts will come through."
        ),
    )


async def templates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List saved replies, or save one with /templates save Name :: body."""
    services = container_from(context)
    text = " ".join(context.args or [])
    if text.lower().startswith("save "):
        name, body = _split_template(text[5:])
        if name and body:
            stored = await services.templates.save(name, body)
            await reply_html(update, formatters.plain(f"Saved template {stored}."))
            return
    rows = await services.templates.list_templates()
    lines = [f"{name}: {body}" for name, body in rows]
    await reply_html(update, formatters.bullet_list("Templates", lines))


async def interests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show or replace the interest profile used for opportunity scores."""
    services = container_from(context)
    if context.args:
        text = " ".join(context.args)
        await services.preferences.set_extra("interests", text)
        services.folders.interests = text
        await reply_html(update, formatters.plain(f"Interests saved: {text}"))
        return
    current = await services.folders.interests_text()
    await reply_html(
        update,
        formatters.plain(f"Interests: {current}\nUpdate with /interests python, machine learning"),
    )


async def search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Run a natural-language search from /search."""
    query = " ".join(context.args) if context.args else ""
    if not query:
        await reply_html(update, formatters.plain("Usage: /search your question"))
        return
    result = await container_from(context).queries.handle(require_user_id(update), query)
    await reply_html(update, formatters.plain(result.text or "No match."))


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the audit log."""
    entries = await container_from(context).audit.history()
    await reply_html(update, formatters.history(entries))


async def preferences(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show preferences and the edit buttons."""
    services = container_from(context)
    prefs = await services.preferences.get()
    text = formatters.preferences(
        prefs, await services.contacts.list_vips(), await services.contacts.list_muted()
    )
    await reply_html(update, text, keyboards.preference_actions())


async def categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show category counts."""
    counts = await container_from(context).inbox.category_counts()
    await reply_html(update, formatters.categories(counts))


async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Stop processing and notifications."""
    await container_from(context).preferences.set_paused(True)
    await reply_html(update, formatters.plain("Paused. Sync and notifications are stopped."))


async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Resume processing and notifications."""
    await container_from(context).preferences.set_paused(False)
    await reply_html(update, formatters.plain("Resumed."))


async def errors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show recent sync and Gemini failures."""
    from app.db.base import session_scope
    from app.db.repositories.state_repository import JobErrorRepository

    services = container_from(context)
    async with session_scope(services.sessions) as session:
        rows = await JobErrorRepository(session).list_recent()
    await reply_html(update, formatters.error_list([(row.source, row.message) for row in rows]))


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show health information."""
    services = container_from(context)
    snapshot = await services.audit.status(
        paused=await services.preferences.is_paused(),
        mode=services.settings.app_mode,
    )
    await reply_html(update, formatters.status(snapshot))


async def done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mark a task or deadline done. Usage: /done t12 or /done d12."""
    await _mutate(update, context, complete=True)


async def snooze(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Snooze a task or deadline until tomorrow morning."""
    await _mutate(update, context, complete=False)


def _split_template(text: str) -> tuple[str, str]:
    if "::" not in text:
        return "", ""
    name, body = text.split("::", 1)
    return name.strip(), body.strip()


async def _mutate(update: Update, context: ContextTypes.DEFAULT_TYPE, *, complete: bool) -> None:
    token = context.args[0] if context.args else ""
    if len(token) < 2 or token[0] not in {"t", "d"} or not token[1:].isdigit():
        await reply_html(update, formatters.plain("Usage: /done t12 or /snooze d3"))
        return
    services = container_from(context)
    identifier = int(token[1:])
    prefs = await services.preferences.get()
    try:
        if token[0] == "t" and complete:
            title = await services.tasks.mark_done(identifier)
            await services.reminders.cancel("task", identifier)
        elif token[0] == "t":
            title = await services.tasks.snooze_until_tomorrow(identifier, prefs.timezone)
        elif complete:
            title = await services.tasks.mark_deadline_done(identifier)
            await services.reminders.cancel("deadline", identifier)
        else:
            until = to_local(utcnow(), prefs.timezone) + timedelta(days=1)
            title = await services.tasks.snooze_deadline(
                identifier, until.replace(hour=9, minute=0)
            )
    except RecordNotFoundError as exc:
        await reply_html(update, formatters.plain(str(exc)))
        return
    verb = "Completed" if complete else "Snoozed"
    await reply_html(update, formatters.plain(f"{verb}: {title}"))


async def report_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log an unexpected handler error without echoing secrets."""
    error = context.error
    detail = redact(str(error))[:300] if error is not None else ""
    logger.error(
        "telegram_handler_failed",
        error_type=type(error).__name__ if error else "",
        detail=detail,
    )
    if not isinstance(update, Update) or not isinstance(context.error, ExecutiveAgentError):
        return
    message = update.effective_message
    if message is not None:
        await message.reply_text(str(context.error))
