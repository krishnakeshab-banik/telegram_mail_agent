"""SQL for reminders."""

from datetime import datetime

from sqlalchemy import select

from app.constants import ReminderStatus
from app.db.models.reminder import Reminder
from app.db.repositories.common import BaseRepository


class ReminderRepository(BaseRepository):
    """Persistence for scheduled reminders."""

    async def get(self, reminder_id: int) -> Reminder | None:
        """Return one reminder."""
        return self.visible(await self.session.get(Reminder, reminder_id))

    async def add(self, reminder: Reminder) -> Reminder:
        """Insert a reminder."""
        self.stamp(reminder)
        self.session.add(reminder)
        await self.session.flush()
        return reminder

    async def list_due(self, moment: datetime) -> list[Reminder]:
        """Return pending reminders whose fire time has arrived."""
        statement = self.restrict(
            select(Reminder)
            .where(Reminder.status == ReminderStatus.PENDING, Reminder.fire_at <= moment)
            .order_by(Reminder.fire_at.asc()),
            Reminder,
        )
        return list(await self.session.scalars(statement))

    async def pending_for(self, target_type: str, target_id: int) -> list[Reminder]:
        """Return pending reminders for one target."""
        statement = self.restrict(
            select(Reminder).where(
                Reminder.target_type == target_type,
                Reminder.target_id == target_id,
                Reminder.status == ReminderStatus.PENDING,
            ),
            Reminder,
        )
        return list(await self.session.scalars(statement))
