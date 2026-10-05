"""SQL for local calendar events."""

from datetime import datetime

from sqlalchemy import select

from app.constants import CalendarEventStatus
from app.db.models.calendar_event import CalendarEvent
from app.db.repositories.common import BaseRepository


class CalendarEventRepository(BaseRepository):
    """Persistence for meeting proposals and created events."""

    async def get(self, event_id: int) -> CalendarEvent | None:
        """Return one local event."""
        return self.visible(await self.session.get(CalendarEvent, event_id))

    async def add(self, event: CalendarEvent) -> CalendarEvent:
        """Insert an event."""
        self.stamp(event)
        self.session.add(event)
        await self.session.flush()
        return event

    async def get_by_email(self, email_id: int) -> CalendarEvent | None:
        """Return the latest event proposed from an email."""
        statement = self.restrict(
            select(CalendarEvent)
            .where(CalendarEvent.email_id == email_id)
            .order_by(CalendarEvent.id.desc()),
            CalendarEvent,
        )
        return await self.session.scalar(statement)

    async def list_between(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        """Return created events overlapping a window."""
        statement = self.restrict(
            select(CalendarEvent).where(
                CalendarEvent.status == CalendarEventStatus.CREATED,
                CalendarEvent.start_at.is_not(None),
                CalendarEvent.start_at < end,
                CalendarEvent.end_at.is_not(None),
                CalendarEvent.end_at > start,
            ),
            CalendarEvent,
        ).order_by(CalendarEvent.start_at.asc())
        return list(await self.session.scalars(statement))
