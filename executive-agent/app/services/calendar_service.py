"""Meeting proposals, conflict checks, and approved calendar mutations."""

from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.constants import ApprovalAction, CalendarEventStatus, PendingKind
from app.db.base import session_scope
from app.db.models.calendar_event import CalendarEvent
from app.db.models.pending_interaction import PendingInteraction
from app.db.repositories.calendar_repository import CalendarEventRepository
from app.db.repositories.state_repository import PendingInteractionRepository
from app.exceptions import RecordNotFoundError
from app.google.calendar_client import CalendarGateway, EventDraft, RemoteEvent
from app.services.approval_service import ApprovalService
from app.services.reminder_service import ReminderService
from app.utils.time import format_local, resolve_relative, utcnow


class CalendarService:
    """Create calendar changes only through an approval executor."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        calendar: CalendarGateway,
        approvals: ApprovalService,
        reminders: ReminderService,
    ) -> None:
        """Store collaborators.

        Args:
            session_factory: Database session factory.
            calendar: Live or demo calendar client.
            approvals: Confirmation gate.
            reminders: Pre-meeting reminder scheduler.
        """
        self._sessions = session_factory
        self._calendar = calendar
        self._approvals = approvals
        self._reminders = reminders

    async def request_create(
        self, event_id: int, telegram_user_id: int, lead_minutes: tuple[int, ...]
    ) -> tuple[int, str]:
        """Open an approval to create a proposed event.

        Args:
            event_id: Local proposed event id.
            telegram_user_id: Owner who must confirm.
            lead_minutes: Reminder offsets stored in the payload.

        Returns:
            Approval id and a conflict warning. The warning is empty when the slot is free.
        """
        event = await self._require(event_id)
        conflicts = await self.conflicts(event)
        warning = _conflict_text(conflicts)
        approval_id = await self._approvals.create(
            action=ApprovalAction.CREATE_EVENT,
            payload={"event_id": event.id, "lead_minutes": list(lead_minutes)},
            summary=f"Create event {event.title}"[:300],
            source_email_id=event.email_id,
            telegram_user_id=telegram_user_id,
        )
        return approval_id, warning

    async def conflicts(self, event: CalendarEvent) -> list[RemoteEvent]:
        """Return remote events that overlap a proposal."""
        if event.start_at is None or event.end_at is None:
            return []
        window_end = event.end_at
        remote = await self._calendar.list_events(
            event.start_at - timedelta(minutes=1), window_end + timedelta(minutes=1)
        )
        return [item for item in remote if item.start < window_end and item.end > event.start_at]

    async def begin_edit(self, event_id: int, telegram_user_id: int) -> None:
        """Ask the next message to replace the proposed meeting time."""
        async with session_scope(self._sessions) as session:
            repo = PendingInteractionRepository(session)
            existing = await repo.get_for_user(telegram_user_id)
            if existing is not None:
                await repo.delete(existing)
            await repo.add(
                PendingInteraction(
                    telegram_user_id=telegram_user_id,
                    kind=PendingKind.EDIT_EVENT,
                    target_id=event_id,
                    expires_at=utcnow() + timedelta(minutes=30),
                )
            )

    async def apply_edit(
        self,
        telegram_user_id: int,
        text: str,
        timezone_name: str,
        lead_minutes: tuple[int, ...],
    ) -> tuple[int, int, str, str, str] | None:
        """Apply a corrected time phrase to a proposed meeting.

        Returns:
            Approval id, event id, title, local time, and conflict warning.
            None when the user is not editing a meeting.
        """
        event_id = await self._take_edit(telegram_user_id)
        if event_id is None:
            return None
        start = resolve_relative(text, now=utcnow(), timezone_name=timezone_name)
        if start is None:
            raise RecordNotFoundError("I could not read that time. Try 'next Tuesday 4pm'.")
        async with session_scope(self._sessions) as session:
            event = await CalendarEventRepository(session).get(event_id)
            if event is None:
                raise RecordNotFoundError("That meeting was not found.")
            event.start_at = start
            event.end_at = start + timedelta(hours=1)
            title = event.title
        approval_id, warning = await self.request_create(event_id, telegram_user_id, lead_minutes)
        return approval_id, event_id, title, format_local(start, timezone_name), warning

    async def _take_edit(self, telegram_user_id: int) -> int | None:
        async with session_scope(self._sessions) as session:
            repo = PendingInteractionRepository(session)
            pending = await repo.get_for_user(telegram_user_id)
            if pending is None or pending.kind != PendingKind.EDIT_EVENT:
                return None
            if pending.expires_at <= utcnow():
                await repo.delete(pending)
                return None
            event_id = pending.target_id
            await repo.delete(pending)
            return event_id

    async def ignore(self, event_id: int) -> None:
        """Drop a proposal without touching Google Calendar."""
        async with session_scope(self._sessions) as session:
            event = await CalendarEventRepository(session).get(event_id)
            if event is not None:
                event.status = CalendarEventStatus.IGNORED

    async def execute_create(self, payload: dict[str, Any]) -> str:
        """Create the Google event described by an approved payload."""
        event = await self._require(int(payload["event_id"]))
        draft = _draft(event)
        google_id = await self._calendar.create_event(draft)
        async with session_scope(self._sessions) as session:
            stored = await CalendarEventRepository(session).get(event.id)
            if stored is None:
                raise RecordNotFoundError("The meeting proposal disappeared.")
            stored.google_event_id = google_id
            stored.status = CalendarEventStatus.CREATED
        leads = tuple(int(item) for item in payload.get("lead_minutes", []))
        if event.start_at is not None and leads:
            await self._reminders.schedule(
                target_type="meeting",
                target_id=event.id,
                due_at=event.start_at,
                lead_minutes=leads,
            )
        return f"Created calendar event {google_id}."

    async def execute_update(self, payload: dict[str, Any]) -> str:
        """Update an existing Google event from an approved payload."""
        event = await self._require(int(payload["event_id"]))
        if not event.google_event_id:
            return await self.execute_create(payload)
        google_id = await self._calendar.update_event(event.google_event_id, _draft(event))
        async with session_scope(self._sessions) as session:
            stored = await CalendarEventRepository(session).get(event.id)
            if stored is not None:
                stored.status = CalendarEventStatus.UPDATED
                stored.google_event_id = google_id
        return f"Updated calendar event {google_id}."

    async def execute_delete(self, payload: dict[str, Any]) -> str:
        """Delete a previously created event."""
        event = await self._require(int(payload["event_id"]))
        if event.google_event_id:
            await self._calendar.delete_event(event.google_event_id)
        async with session_scope(self._sessions) as session:
            stored = await CalendarEventRepository(session).get(event.id)
            if stored is not None:
                stored.status = CalendarEventStatus.DELETED
        await self._reminders.cancel("meeting", event.id)
        return "Deleted the calendar event."

    async def list_window(self, start: object, end: object) -> list[RemoteEvent]:
        """List remote events. Datetimes are validated by the caller."""
        from datetime import datetime

        if not isinstance(start, datetime) or not isinstance(end, datetime):
            return []
        return await self._calendar.list_events(start, end)

    async def for_email(self, email_id: int) -> CalendarEvent | None:
        """Return the proposal stored for an email."""
        async with session_scope(self._sessions) as session:
            return await CalendarEventRepository(session).get_by_email(email_id)

    async def _require(self, event_id: int) -> CalendarEvent:
        async with session_scope(self._sessions) as session:
            event = await CalendarEventRepository(session).get(event_id)
        if event is None:
            raise RecordNotFoundError("That meeting was not found.")
        return event


def _draft(event: CalendarEvent) -> EventDraft:
    start = event.start_at or utcnow()
    end = event.end_at or (start + timedelta(hours=1))
    attendees = [item for item in event.attendees.split(",") if item]
    return EventDraft(
        title=event.title,
        description=event.description,
        start=start,
        end=end,
        timezone_name=event.timezone_name,
        location=event.location,
        link=event.link,
        attendees=attendees,
    )


def _conflict_text(conflicts: list[RemoteEvent]) -> str:
    if not conflicts:
        return ""
    titles = ", ".join(item.title or "Busy" for item in conflicts[:3])
    return f"Conflict with: {titles}"
