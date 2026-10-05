"""SQL for deadlines."""

from datetime import datetime

from sqlalchemy import select

from app.constants import TaskStatus
from app.db.models.deadline import Deadline
from app.db.repositories.common import BaseRepository


class DeadlineRepository(BaseRepository):
    """Persistence for extracted deadlines."""

    async def get(self, deadline_id: int) -> Deadline | None:
        """Return one deadline."""
        return self.visible(await self.session.get(Deadline, deadline_id))

    async def add(self, deadline: Deadline) -> Deadline:
        """Insert a deadline."""
        self.stamp(deadline)
        self.session.add(deadline)
        await self.session.flush()
        return deadline

    async def list_open_until(self, moment: datetime) -> list[Deadline]:
        """Return open deadlines due at or before a moment."""
        statement = self.restrict(
            select(Deadline).where(
                Deadline.status == TaskStatus.OPEN,
                Deadline.due_at.is_not(None),
                Deadline.due_at <= moment,
            ),
            Deadline,
        ).order_by(Deadline.due_at.asc())
        return list(await self.session.scalars(statement))

    async def earliest_for_email(self, email_id: int) -> Deadline | None:
        """Return the soonest dated deadline on one email."""
        statement = self.restrict(
            select(Deadline)
            .where(Deadline.email_id == email_id, Deadline.due_at.is_not(None))
            .order_by(Deadline.due_at.asc()),
            Deadline,
        )
        return await self.session.scalar(statement)

    async def list_open(self) -> list[Deadline]:
        """Return every unfinished deadline."""
        statement = self.restrict(
            select(Deadline)
            .where(Deadline.status.in_([TaskStatus.OPEN, TaskStatus.SNOOZED]))
            .order_by(Deadline.due_at.asc().nulls_last()),
            Deadline,
        )
        return list(await self.session.scalars(statement))
