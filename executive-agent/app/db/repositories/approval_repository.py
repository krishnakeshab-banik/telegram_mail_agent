"""SQL for approvals."""

from datetime import datetime

from sqlalchemy import select

from app.constants import ApprovalStatus
from app.db.models.approval import Approval
from app.db.repositories.common import BaseRepository


class ApprovalRepository(BaseRepository):
    """Persistence for the confirmation gate."""

    async def get(self, approval_id: int) -> Approval | None:
        """Return one approval."""
        return self.visible(await self.session.get(Approval, approval_id))

    async def add(self, approval: Approval) -> Approval:
        """Insert an approval."""
        self.stamp(approval)
        self.session.add(approval)
        await self.session.flush()
        return approval

    async def list_pending(self) -> list[Approval]:
        """Return approvals that are still waiting."""
        statement = self.restrict(
            select(Approval).where(Approval.status == ApprovalStatus.PENDING), Approval
        )
        return list(await self.session.scalars(statement))

    async def list_expired(self, moment: datetime) -> list[Approval]:
        """Return pending approvals whose expiry has passed."""
        statement = self.restrict(
            select(Approval).where(
                Approval.status == ApprovalStatus.PENDING,
                Approval.expires_at <= moment,
            ),
            Approval,
        )
        return list(await self.session.scalars(statement))
