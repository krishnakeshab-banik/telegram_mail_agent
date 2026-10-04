"""Tasks extracted from mail or created from Telegram."""

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.constants import TaskStatus
from app.db.base import session_scope
from app.db.models.deadline import Deadline
from app.db.models.task import Task
from app.db.repositories.deadline_repository import DeadlineRepository
from app.db.repositories.task_repository import TaskRepository
from app.exceptions import RecordNotFoundError
from app.utils.time import utcnow


class TaskService:
    """Create, list, complete, and snooze tasks."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Store the session factory.

        Args:
            session_factory: Database session factory.
        """
        self._sessions = session_factory

    async def add(
        self,
        *,
        title: str,
        due_at: datetime | None,
        email_id: int | None,
        source: str,
    ) -> int:
        """Insert a task and return its id."""
        async with session_scope(self._sessions) as session:
            task = await TaskRepository(session).add(
                Task(
                    title=title[:300],
                    due_at=due_at,
                    email_id=email_id,
                    source=source,
                    status=TaskStatus.OPEN,
                )
            )
            return task.id

    async def list_open(self) -> list[Task]:
        """Return tasks that are open or past their snooze."""
        async with session_scope(self._sessions) as session:
            return await TaskRepository(session).list_open(now=utcnow())

    async def mark_done(self, task_id: int) -> str:
        """Complete a task."""
        async with session_scope(self._sessions) as session:
            task = await self._require(session, task_id)
            task.status = TaskStatus.DONE
            task.completed_at = utcnow()
            return task.title

    async def snooze(self, task_id: int, until: datetime) -> str:
        """Hide a task until a moment."""
        async with session_scope(self._sessions) as session:
            task = await self._require(session, task_id)
            task.status = TaskStatus.SNOOZED
            task.snooze_until = until
            return task.title

    async def snooze_hours(self, task_id: int, hours: int) -> str:
        """Snooze a task by a number of hours from now."""
        return await self.snooze(task_id, utcnow() + timedelta(hours=hours))

    async def snooze_until_tomorrow(self, task_id: int, timezone_name: str) -> str:
        """Snooze a task until 09:00 tomorrow in the user's timezone."""
        from app.utils.time import to_local, zone

        local = to_local(utcnow(), timezone_name)
        tomorrow = (local + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        return await self.snooze(task_id, tomorrow.replace(tzinfo=zone(timezone_name)))

    async def list_deadlines(self) -> list[Deadline]:
        """Return unfinished deadlines."""
        async with session_scope(self._sessions) as session:
            return await DeadlineRepository(session).list_open()

    async def mark_deadline_done(self, deadline_id: int) -> str:
        """Complete a deadline."""
        async with session_scope(self._sessions) as session:
            deadline = await DeadlineRepository(session).get(deadline_id)
            if deadline is None:
                raise RecordNotFoundError(f"Deadline {deadline_id} was not found.")
            deadline.status = TaskStatus.DONE
            return deadline.title

    async def snooze_deadline(self, deadline_id: int, until: datetime) -> str:
        """Snooze a deadline."""
        async with session_scope(self._sessions) as session:
            deadline = await DeadlineRepository(session).get(deadline_id)
            if deadline is None:
                raise RecordNotFoundError(f"Deadline {deadline_id} was not found.")
            deadline.status = TaskStatus.SNOOZED
            deadline.snooze_until = until
            return deadline.title

    async def complete_for_email(self, email_id: int) -> int:
        """Mark every open task from an email done."""
        tasks = await self.list_open()
        count = 0
        for task in tasks:
            if task.email_id == email_id:
                await self.mark_done(task.id)
                count += 1
        return count

    async def _require(self, session: AsyncSession, task_id: int) -> Task:
        task = await TaskRepository(session).get(task_id)
        if task is None:
            raise RecordNotFoundError(f"Task {task_id} was not found.")
        return task
