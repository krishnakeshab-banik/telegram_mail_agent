"""Persist tasks, deadlines, meetings, and follow-ups from a classification."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.schemas import EmailClassification
from app.constants import (
    CalendarEventStatus,
    EmailDirection,
    FollowUpDirection,
    FollowUpStatus,
    TaskStatus,
)
from app.db.models.calendar_event import CalendarEvent
from app.db.models.deadline import Deadline
from app.db.models.email import EmailMessage
from app.db.models.followup import FollowUp
from app.db.models.task import Task
from app.db.repositories.calendar_repository import CalendarEventRepository
from app.db.repositories.deadline_repository import DeadlineRepository
from app.db.repositories.followup_repository import FollowUpRepository
from app.db.repositories.task_repository import TaskRepository
from app.google.gmail_parser import find_meeting_links
from app.utils.time import parse_iso, resolve_relative


async def store_extractions(
    session: AsyncSession,
    message: EmailMessage,
    classification: EmailClassification,
    timezone_name: str,
) -> tuple[list[int], list[int], int | None]:
    """Save structured extractions for one analyzed message.

    Args:
        session: Open unit of work.
        message: Stored email.
        classification: Validated model output.
        timezone_name: User timezone for relative dates.

    Returns:
        Task ids, deadline ids, and the proposed calendar event id.
    """
    anchor = (
        message.received_at
        if message.received_at.tzinfo
        else message.received_at.replace(tzinfo=UTC)
    )
    task_ids = await _tasks(session, message, classification, timezone_name, anchor)
    deadline_ids = await _deadlines(session, message, classification, timezone_name, anchor)
    event_id = await _meeting(session, message, classification, timezone_name, anchor)
    await _followup(session, message, classification, timezone_name, anchor)
    return task_ids, deadline_ids, event_id


async def _tasks(
    session: AsyncSession,
    message: EmailMessage,
    classification: EmailClassification,
    timezone_name: str,
    now: datetime,
) -> list[int]:
    repo = TaskRepository(session)
    identifiers: list[int] = []
    for item in classification.action_items:
        title = item.task.strip()
        if not _usable_task(title):
            continue
        task = await repo.add(
            Task(
                email_id=message.id,
                title=title[:300],
                due_at=resolve_when(item.due_date or item.relative_phrase, timezone_name, now),
                source="email",
                status=TaskStatus.OPEN,
            )
        )
        identifiers.append(task.id)
    return identifiers


async def _deadlines(
    session: AsyncSession,
    message: EmailMessage,
    classification: EmailClassification,
    timezone_name: str,
    now: datetime,
) -> list[int]:
    repo = DeadlineRepository(session)
    identifiers: list[int] = []
    for item in classification.deadlines:
        title = item.title.strip()
        if not title:
            continue
        row = await repo.add(
            Deadline(
                email_id=message.id,
                title=title[:300],
                due_at=resolve_when(item.datetime_iso or item.relative_phrase, timezone_name, now),
                confidence=item.confidence,
                status=TaskStatus.OPEN,
            )
        )
        identifiers.append(row.id)
    return identifiers


async def _meeting(
    session: AsyncSession,
    message: EmailMessage,
    classification: EmailClassification,
    timezone_name: str,
    now: datetime,
) -> int | None:
    meeting = classification.meeting
    if not meeting.is_present:
        return None
    start = resolve_when(meeting.start_iso or meeting.relative_phrase, timezone_name, now)
    end = resolve_when(meeting.end_iso, timezone_name, now)
    if start is not None and end is None:
        end = start + timedelta(hours=1)
    discovered = find_meeting_links(message.body_text)
    link = meeting.link or (discovered[0] if discovered else "")
    event = await CalendarEventRepository(session).add(
        CalendarEvent(
            email_id=message.id,
            title=meeting.title[:300],
            description=classification.summary[:1000],
            start_at=start,
            end_at=end,
            timezone_name=meeting.timezone or timezone_name,
            location=meeting.location,
            link=link,
            attendees=",".join(meeting.attendees),
            confidence=meeting.confidence,
            status=CalendarEventStatus.PROPOSED,
        )
    )
    return event.id


async def _followup(
    session: AsyncSession,
    message: EmailMessage,
    classification: EmailClassification,
    timezone_name: str,
    now: datetime,
) -> None:
    repo = FollowUpRepository(session)
    if await repo.find_open_for_email(message.id) is not None:
        return
    if message.direction == EmailDirection.INBOUND and classification.requires_reply:
        await repo.add(
            FollowUp(
                email_id=message.id,
                direction=FollowUpDirection.INBOUND_NEEDS_REPLY,
                counterpart_email=message.sender_email,
                subject=message.subject[:300],
                status=FollowUpStatus.OPEN,
            )
        )
        return
    if message.direction == EmailDirection.OUTBOUND and classification.outbound_promise:
        await repo.add(
            FollowUp(
                email_id=message.id,
                direction=FollowUpDirection.OUTBOUND_AWAITING,
                counterpart_email=_first_address(message.to_recipients),
                subject=message.subject[:300],
                promise_text=classification.outbound_promise[:500],
                due_at=resolve_when(classification.promise_due, timezone_name, now),
                status=FollowUpStatus.OPEN,
            )
        )


def _usable_task(title: str) -> bool:
    """Drop newsletter buttons and one-word leftovers."""
    lowered = title.strip().lower()
    if lowered in {"click here", "unsubscribe", "view in browser", "learn more", "read more"}:
        return False
    return len(title.strip()) >= 12 and len(title.split()) >= 3


def resolve_when(phrase: str, timezone_name: str, now: datetime) -> datetime | None:
    """Resolve an ISO value or a relative phrase.

    Args:
        phrase: Model-provided date text.
        timezone_name: User timezone.
        now: Current instant.

    Returns:
        Aware UTC datetime, or None when the phrase is empty.
    """
    if not phrase.strip():
        return None
    return parse_iso(phrase, timezone_name) or resolve_relative(
        phrase, now=now, timezone_name=timezone_name
    )


def _first_address(value: str) -> str:
    from email.utils import getaddresses

    parsed = getaddresses([value])
    return parsed[0][1].lower() if parsed and parsed[0][1] else ""
