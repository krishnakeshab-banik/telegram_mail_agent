"""SQL for tasks."""

from datetime import datetime

from sqlalchemy import select

from app.constants import TaskStatus
from app.db.models.task import Task
from app.db.repositories.common import BaseRepository


class TaskRepository(BaseRepository):
    """Persistence for tasks."""

    async def get(self, task_id: int) -> Task | None:
        """Return one task."""
        return await self.session.get(Task, task_id)

    async def add(self, task: Task) -> Task:
        """Insert a task."""
        self.session.add(task)
        await self.session.flush()
        return task

    async def list_open(self, *, now: datetime) -> list[Task]:
        """Return open tasks whose snooze has elapsed."""
        statement = (
            select(Task)
            .where(Task.status.in_([TaskStatus.OPEN, TaskStatus.SNOOZED]))
            .order_by(Task.due_at.asc().nulls_last(), Task.id.asc())
        )
        rows = list(await self.session.scalars(statement))
        return [
            row for row in rows if row.status == TaskStatus.OPEN or _elapsed(row.snooze_until, now)
        ]


def _elapsed(snooze_until: datetime | None, now: datetime) -> bool:
    return snooze_until is None or snooze_until <= now
