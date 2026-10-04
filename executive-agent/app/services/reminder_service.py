"""Schedule and collect Telegram reminders for tasks, deadlines, and meetings."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.constants import ReminderStatus
from app.db.base import session_scope
from app.db.models.reminder import Reminder
from app.db.repositories.calendar_repository import CalendarEventRepository
from app.db.repositories.deadline_repository import DeadlineRepository
from app.db.repositories.reminder_repository import ReminderRepository
from app.db.repositories.task_repository import TaskRepository
from app.utils.time import utcnow


@dataclass(frozen=True)
class DueReminder:
    """A reminder ready to send."""

    reminder_id: int
    target_type: str
    target_id: int
    title: str
    when_label: str
    link: str
    context: str


class ReminderService:
    """Create lead-time reminders and return the ones that are due."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Store the session factory.

        Args:
            session_factory: Database session factory.
        """
        self._sessions = session_factory

    async def schedule(
        self,
        *,
        target_type: str,
        target_id: int,
        due_at: datetime,
        lead_minutes: tuple[int, ...],
    ) -> None:
        """Create reminders that have not already been scheduled.

        Args:
            target_type: task, deadline, or meeting.
            target_id: Target primary key.
            due_at: Moment the item is due.
            lead_minutes: How long before due_at each reminder fires.
        """
        async with session_scope(self._sessions) as session:
            repo = ReminderRepository(session)
            existing = {
                (item.lead_minutes) for item in await repo.pending_for(target_type, target_id)
            }
            now = utcnow()
            for lead in lead_minutes:
                if lead in existing:
                    continue
                fire_at = due_at - timedelta(minutes=lead)
                if fire_at <= now:
                    continue
                await repo.add(
                    Reminder(
                        target_type=target_type,
                        target_id=target_id,
                        fire_at=fire_at,
                        lead_minutes=lead,
                        status=ReminderStatus.PENDING,
                    )
                )

    async def due(self) -> list[DueReminder]:
        """Return reminders whose fire time has arrived."""
        async with session_scope(self._sessions) as session:
            rows = await ReminderRepository(session).list_due(utcnow())
            rendered: list[DueReminder] = []
            for row in rows:
                rendered.append(await _render(session, row))
            return rendered

    async def mark_sent(self, reminder_id: int) -> None:
        """Mark a reminder sent so it is not delivered again."""
        async with session_scope(self._sessions) as session:
            row = await ReminderRepository(session).get(reminder_id)
            if row is None:
                return
            row.status = ReminderStatus.SENT
            row.sent_at = utcnow()

    async def cancel(self, target_type: str, target_id: int) -> None:
        """Cancel pending reminders for a completed target."""
        async with session_scope(self._sessions) as session:
            for row in await ReminderRepository(session).pending_for(target_type, target_id):
                row.status = ReminderStatus.CANCELLED


async def _render(session: AsyncSession, row: Reminder) -> DueReminder:
    title, link, context = await _target_text(session, row.target_type, row.target_id)
    return DueReminder(
        reminder_id=row.id,
        target_type=row.target_type,
        target_id=row.target_id,
        title=title,
        when_label=f"{row.lead_minutes} minutes before" if row.lead_minutes else "now",
        link=link,
        context=context,
    )


async def _target_text(
    session: AsyncSession, target_type: str, target_id: int
) -> tuple[str, str, str]:
    if target_type == "task":
        task = await TaskRepository(session).get(target_id)
        return (task.title if task else "Task", "", "")
    if target_type == "deadline":
        deadline = await DeadlineRepository(session).get(target_id)
        return (deadline.title if deadline else "Deadline", "", "")
    event = await CalendarEventRepository(session).get(target_id)
    if event is None:
        return ("Meeting", "", "")
    return (event.title, event.link, event.description[:240])
