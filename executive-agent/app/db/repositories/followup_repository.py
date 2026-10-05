"""SQL for follow-ups."""

from datetime import datetime

from sqlalchemy import select

from app.constants import FollowUpStatus
from app.db.models.followup import FollowUp
from app.db.repositories.common import BaseRepository


class FollowUpRepository(BaseRepository):
    """Persistence for unanswered and awaiting-response items."""

    async def get(self, followup_id: int) -> FollowUp | None:
        """Return one follow-up."""
        return self.visible(await self.session.get(FollowUp, followup_id))

    async def add(self, followup: FollowUp) -> FollowUp:
        """Insert a follow-up."""
        self.stamp(followup)
        self.session.add(followup)
        await self.session.flush()
        return followup

    async def find_open_for_email(self, email_id: int) -> FollowUp | None:
        """Return an open follow-up already created for an email."""
        statement = self.restrict(
            select(FollowUp).where(
                FollowUp.email_id == email_id,
                FollowUp.status.in_([FollowUpStatus.OPEN, FollowUpStatus.SNOOZED]),
            ),
            FollowUp,
        )
        return await self.session.scalar(statement)

    async def list_open(self, now: datetime) -> list[FollowUp]:
        """Return follow-ups that are open or whose snooze elapsed."""
        statement = self.restrict(
            select(FollowUp)
            .where(FollowUp.status.in_([FollowUpStatus.OPEN, FollowUpStatus.SNOOZED]))
            .order_by(FollowUp.due_at.asc().nulls_last(), FollowUp.id.asc()),
            FollowUp,
        )
        rows = list(await self.session.scalars(statement))
        visible: list[FollowUp] = []
        for row in rows:
            if (
                row.status == FollowUpStatus.OPEN
                or row.snooze_until is None
                or row.snooze_until <= now
            ):
                visible.append(row)
        return visible
