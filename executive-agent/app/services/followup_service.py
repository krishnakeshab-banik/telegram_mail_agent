"""Track replies the owner owes and responses the owner is waiting on."""

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.constants import FollowUpDirection, FollowUpStatus
from app.db.base import session_scope
from app.db.models.followup import FollowUp
from app.db.repositories.followup_repository import FollowUpRepository
from app.exceptions import RecordNotFoundError
from app.utils.time import utcnow


class FollowUpService:
    """Create and update follow-up records."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Store the session factory.

        Args:
            session_factory: Database session factory.
        """
        self._sessions = session_factory

    async def ensure(
        self,
        *,
        email_id: int,
        direction: str,
        counterpart_email: str,
        subject: str,
        promise_text: str,
        due_at: datetime | None,
    ) -> int | None:
        """Create a follow-up when one is not already open for the email.

        Returns:
            Follow-up id, or None when an open one already exists.
        """
        async with session_scope(self._sessions) as session:
            repo = FollowUpRepository(session)
            if await repo.find_open_for_email(email_id) is not None:
                return None
            row = await repo.add(
                FollowUp(
                    email_id=email_id,
                    direction=direction,
                    counterpart_email=counterpart_email.lower(),
                    subject=subject[:300],
                    promise_text=promise_text[:500],
                    due_at=due_at,
                    status=FollowUpStatus.OPEN,
                )
            )
            return row.id

    async def list_open(self) -> list[FollowUp]:
        """Return visible follow-ups."""
        async with session_scope(self._sessions) as session:
            return await FollowUpRepository(session).list_open(utcnow())

    async def dismiss(self, followup_id: int) -> None:
        """Stop tracking a follow-up."""
        await self._set_status(followup_id, FollowUpStatus.DISMISSED)

    async def complete_for_email(self, email_id: int) -> None:
        """Close follow-ups attached to an email."""
        for item in await self.list_open():
            if item.email_id == email_id:
                await self._set_status(item.id, FollowUpStatus.DONE)

    async def snooze(self, followup_id: int, until: datetime) -> None:
        """Hide a follow-up until a moment."""
        async with session_scope(self._sessions) as session:
            row = await self._require(session, followup_id)
            row.status = FollowUpStatus.SNOOZED
            row.snooze_until = until

    async def snooze_hours(self, followup_id: int, hours: int) -> None:
        """Snooze a follow-up for a number of hours."""
        await self.snooze(followup_id, utcnow() + timedelta(hours=hours))

    async def due_nudges(self, interval_hours: int) -> list[FollowUp]:
        """Return open follow-ups that have not been nudged inside the interval."""
        cutoff = utcnow() - timedelta(hours=interval_hours)
        due: list[FollowUp] = []
        for item in await self.list_open():
            if item.direction not in {
                FollowUpDirection.INBOUND_NEEDS_REPLY,
                FollowUpDirection.OUTBOUND_AWAITING,
            }:
                continue
            anchor = item.last_nudged_at or item.created_at
            if anchor <= cutoff:
                due.append(item)
        return due

    async def mark_nudged(self, followup_id: int) -> None:
        """Record that a nudge was delivered."""
        async with session_scope(self._sessions) as session:
            row = await self._require(session, followup_id)
            row.last_nudged_at = utcnow()

    async def _set_status(self, followup_id: int, status: str) -> None:
        async with session_scope(self._sessions) as session:
            row = await self._require(session, followup_id)
            row.status = status

    async def _require(self, session: AsyncSession, followup_id: int) -> FollowUp:
        row = await FollowUpRepository(session).get(followup_id)
        if row is None:
            raise RecordNotFoundError(f"Follow-up {followup_id} was not found.")
        return row
