"""Morning briefing and evening wrap-up."""

from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.summarizer import Summarizer
from app.constants import EmailDirection, FollowUpDirection, TaskStatus
from app.db.base import session_scope
from app.db.repositories.analysis_repository import AnalysisRepository
from app.db.repositories.deadline_repository import DeadlineRepository
from app.db.repositories.email_repository import EmailRepository
from app.services.calendar_service import CalendarService
from app.services.followup_service import FollowUpService
from app.services.preference_service import PreferenceService
from app.services.task_service import TaskService
from app.utils.security import wrap_untrusted
from app.utils.time import format_local, to_local, utcnow


@dataclass(frozen=True)
class Digest:
    """Sections of a morning briefing or evening wrap-up."""

    title: str
    important: list[str]
    meetings: list[str]
    deadlines: list[str]
    tasks: list[str]
    followups: list[str]
    focus: str
    waiting_on_you: list[str] = field(default_factory=list)
    waiting_on_others: list[str] = field(default_factory=list)
    unread: list[str] = field(default_factory=list)


class BriefingService:
    """Assemble the daily executive briefing from local records."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        preferences: PreferenceService,
        tasks: TaskService,
        followups: FollowUpService,
        calendar: CalendarService,
        summarizer: Summarizer,
    ) -> None:
        """Store collaborators.

        Args:
            session_factory: Database session factory.
            preferences: Timezone and thresholds.
            tasks: Open tasks.
            followups: Open follow-ups.
            calendar: Today's remote events.
            summarizer: Optional focus-line model.
        """
        self._sessions = session_factory
        self._preferences = preferences
        self._tasks = tasks
        self._followups = followups
        self._calendar = calendar
        self._summarizer = summarizer

    async def morning(self) -> Digest:
        """Build the morning briefing."""
        return await self._digest("Morning briefing", focus=True)

    async def wrapup(self) -> Digest:
        """Build the evening wrap-up from what is still open."""
        return await self._digest("Evening wrap-up", focus=False)

    async def important_lines(self) -> list[str]:
        """Return the same Important lines the morning briefing uses."""
        prefs = await self._preferences.get()
        return await self._important(prefs.importance_threshold)

    async def unread_lines(self) -> list[str]:
        """Return the same Unread lines the morning briefing uses."""
        async with session_scope(self._sessions) as session:
            messages = await EmailRepository(session).list_unread(limit=8)
        return [
            f"{message.sender_name or message.sender_email}: {message.subject}"
            for message in messages
        ]

    async def waiting_lines(self) -> tuple[list[str], list[str]]:
        """Return replies owed and replies still outstanding."""
        open_loops = await self._followups.list_open()
        waiting_on_you = [
            item.subject or item.counterpart_email
            for item in open_loops
            if item.direction == FollowUpDirection.INBOUND_NEEDS_REPLY
        ][:8]
        waiting_on_others = [
            item.subject or item.counterpart_email
            for item in open_loops
            if item.direction == FollowUpDirection.OUTBOUND_AWAITING
        ][:8]
        return waiting_on_you, waiting_on_others

    async def today_lines(self) -> tuple[list[tuple[str, str]], list[str], list[str]]:
        """Return today's meetings, deadlines inside 24 hours, and pending replies."""
        prefs = await self._preferences.get()
        local_now = to_local(utcnow(), prefs.timezone)
        day_end = local_now.replace(hour=23, minute=59, second=0, microsecond=0)
        events = await self._calendar.list_window(local_now, day_end)
        meetings = [
            (
                f"{format_local(item.start, prefs.timezone, '%H:%M')} {item.title}",
                item.link,
            )
            for item in events
        ]
        horizon = utcnow() + timedelta(hours=24)
        async with session_scope(self._sessions) as session:
            rows = await DeadlineRepository(session).list_open()
        deadlines = [
            row.title
            for row in rows
            if row.status != TaskStatus.DONE and row.due_at is not None and row.due_at <= horizon
        ][:8]
        pending, _others = await self.waiting_lines()
        return meetings, deadlines, pending

    async def _digest(self, title: str, *, focus: bool) -> Digest:
        prefs = await self._preferences.get()
        local_now = to_local(utcnow(), prefs.timezone)
        day_end = local_now.replace(hour=23, minute=59, second=0, microsecond=0)
        week_end = local_now + timedelta(days=7)
        important = await self.important_lines()
        unread = await self.unread_lines()
        meetings = await self._meetings(local_now, day_end)
        deadlines = await self._deadlines(week_end)
        tasks = [task.title for task in await self._tasks.list_open()][:8]
        waiting_on_you, waiting_on_others = await self.waiting_lines()
        followups = waiting_on_you + waiting_on_others
        focus_line = ""
        facts = "\n".join(important + meetings + deadlines + tasks + followups)
        if focus and facts.strip():
            focus_line = await self._summarizer.focus_line(wrap_untrusted("facts", facts))
        return Digest(
            title,
            important,
            meetings,
            deadlines,
            tasks,
            followups,
            focus_line,
            waiting_on_you,
            waiting_on_others,
            unread,
        )

    async def _important(self, threshold: int) -> list[str]:
        async with session_scope(self._sessions) as session:
            messages = await EmailRepository(session).list_important(threshold, limit=5)
            lines: list[str] = []
            for message in messages:
                if message.direction != EmailDirection.INBOUND:
                    continue
                analysis = await AnalysisRepository(session).get_by_email(message.id)
                summary = analysis.summary if analysis else message.snippet
                lines.append(
                    f"{message.sender_name or message.sender_email}: {message.subject} — {summary}"
                )
        if lines:
            return lines
        return await self._recent()

    async def _recent(self) -> list[str]:
        async with session_scope(self._sessions) as session:
            messages = await EmailRepository(session).list_recent_inbound(limit=6)
        return [
            f"{message.sender_name or message.sender_email}: {message.subject}"
            for message in messages
        ]

    async def _meetings(self, start: object, end: object) -> list[str]:
        from datetime import datetime

        if not isinstance(start, datetime) or not isinstance(end, datetime):
            return []
        events = await self._calendar.list_window(start, end)
        prefs = await self._preferences.get()
        return [
            f"{format_local(item.start, prefs.timezone, '%H:%M')} {item.title}" for item in events
        ]

    async def _deadlines(self, until: object) -> list[str]:
        from datetime import datetime

        if not isinstance(until, datetime):
            return []
        async with session_scope(self._sessions) as session:
            rows = await DeadlineRepository(session).list_open()
        lines = []
        for row in rows:
            if row.status == TaskStatus.DONE:
                continue
            if row.due_at is None or row.due_at <= until:
                lines.append(row.title)
        return lines[:8]
