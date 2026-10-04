"""Scheduled jobs. Each job calls services and formats the result."""

from datetime import datetime, timedelta

from app.bot import formatters, keyboards
from app.db.base import session_scope
from app.db.repositories.email_repository import EmailRepository
from app.db.repositories.state_repository import SyncStateRepository
from app.exceptions import AuthExpiredError, ExecutiveAgentError
from app.services.container import Container
from app.utils.logging import get_logger
from app.utils.time import to_local, utcnow

logger = get_logger(__name__)
_RECENT_NOTICES: dict[str, datetime] = {}


async def poll_inbox(container: Container) -> None:
    """Sync mail, classify it, and deliver any alerts that are due."""
    if await container.preferences.is_paused():
        return
    try:
        inserted = await container.sync.sync_inbox()
        await container.signups.sync_connected()
        processed = await container.pipeline.process_pending()
        await container.folders.organize(processed)
        await container.otp.purge_expired()
        for email_id in processed:
            await container.attachments.process_email(email_id)
        await deliver_alerts(container)
        await _report_backfill(container, len(inserted))
        await _report_gemini(container)
    except AuthExpiredError as exc:
        await container.audit.record_failure("sync", exc)
        await _notify_once(
            container,
            "auth",
            "Google authorization expired. Send /signup and approve access in the browser.",
        )
    except ExecutiveAgentError as exc:
        await container.audit.record_failure("sync", exc)
        logger.warning("sync_failed", error_type=type(exc).__name__)
        await _notify_once(container, f"sync:{type(exc).__name__}", f"Sync failed: {exc}")


async def deliver_alerts(container: Container) -> None:
    """Send claimed alerts. Failures release the claim so they can retry."""
    chat_id = await container.preferences.chat_id()
    plans = await container.notifier.claim_ready()
    if chat_id is None:
        for plan in plans:
            await container.notifier.release(plan.email_id)
        return
    labels_enabled = (await container.preferences.get()).apply_labels
    for plan in plans:
        try:
            await container.sender.send_text(
                chat_id,
                formatters.email_alert(plan),
                keyboards.email_actions(
                    plan.email_id, has_meeting=plan.has_meeting, labels_enabled=labels_enabled
                ),
            )
            await container.notifier.mark_sent(plan.email_id)
        except Exception as exc:
            await container.notifier.release(plan.email_id)
            await container.audit.record_failure("notify", exc)


async def dispatch_reminders(container: Container) -> None:
    """Send due reminders."""
    if await container.preferences.is_paused():
        return
    chat_id = await container.preferences.chat_id()
    if chat_id is None:
        return
    for reminder in await container.reminders.due():
        try:
            await container.sender.send_text(
                chat_id,
                formatters.reminder(reminder),
                keyboards.reminder_actions(reminder.target_type, reminder.target_id),
            )
            await container.reminders.mark_sent(reminder.reminder_id)
        except Exception as exc:
            await container.audit.record_failure("reminder", exc)


async def nudge_followups(container: Container) -> None:
    """Nudge the owner about open follow-ups."""
    if await container.preferences.is_paused():
        return
    chat_id = await container.preferences.chat_id()
    if chat_id is None:
        return
    hours = (await container.preferences.get()).followup_nudge_hours
    for item in await container.followups.due_nudges(hours):
        text = f"Follow-up: {item.subject or item.counterpart_email}"
        try:
            await container.sender.send_text(
                chat_id, formatters.plain(text), keyboards.followup_actions(item.id)
            )
            await container.followups.mark_nudged(item.id)
        except Exception as exc:
            await container.audit.record_failure("followup", exc)


async def send_digests(container: Container) -> None:
    """Send the morning briefing and evening wrap-up once per local day."""
    if await container.preferences.is_paused():
        return
    chat_id = await container.preferences.chat_id()
    if chat_id is None:
        return
    prefs = await container.preferences.get()
    local = to_local(utcnow(), prefs.timezone)
    day = local.date().isoformat()
    if (local.hour, local.minute) == (prefs.briefing_hour, prefs.briefing_minute):
        if await container.preferences.mark_digest("briefing", day):
            await container.sender.send_text(
                chat_id, formatters.digest(await container.briefing.morning())
            )
    if (local.hour, local.minute) == (prefs.wrapup_hour, prefs.wrapup_minute):
        if await container.preferences.mark_digest("wrapup", day):
            await container.sender.send_text(
                chat_id, formatters.digest(await container.briefing.wrapup())
            )


async def expire_approvals(container: Container) -> None:
    """Expire confirmations that the owner did not answer in time."""
    await container.approvals.expire_due()


async def _report_backfill(container: Container, inserted: int) -> None:
    if not container.sync.consume_backfill():
        return
    prefs = await container.preferences.get()
    async with session_scope(container.sessions) as session:
        important = await EmailRepository(session).count_important(prefs.importance_threshold)
    await _notify(
        container,
        f"Connected: found {inserted} new emails in the last 7 days, {important} important.",
    )


async def _report_gemini(container: Container) -> None:
    async with session_scope(container.sessions) as session:
        state = await SyncStateRepository(session).get_singleton()
        detail = state.last_gemini_error
    if not detail:
        return
    await _notify_once(
        container,
        "gemini",
        "Gemini request failed: "
        f"{detail} The bot will retry on the next poll. If this continues, check the API quota.",
    )


async def _notify_once(container: Container, key: str, text: str) -> None:
    now = utcnow()
    previous = _RECENT_NOTICES.get(key)
    if previous is not None and now - previous < timedelta(minutes=10):
        return
    _RECENT_NOTICES[key] = now
    await _notify(container, text)


async def _notify(container: Container, text: str) -> None:
    chat_id = await container.preferences.chat_id()
    if chat_id is not None:
        await container.sender.send_text(chat_id, formatters.plain(text))
