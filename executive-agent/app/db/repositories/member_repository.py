"""SQL for Telegram users who connected Google."""

from sqlalchemy import select

from app.db.models.member import Member
from app.db.repositories.common import BaseRepository


class MemberRepository(BaseRepository):
    """Persistence for signup records."""

    async def get_by_telegram(self, telegram_user_id: int) -> Member | None:
        """Return the member row for a Telegram user."""
        statement = select(Member).where(Member.telegram_user_id == telegram_user_id)
        return await self.session.scalar(statement)

    async def list_linked(self) -> list[Member]:
        """Return members that have a stored refresh token."""
        statement = select(Member).where(Member.encrypted_refresh_token != "")
        return list(await self.session.scalars(statement))

    async def add(self, member: Member) -> Member:
        """Insert a member row."""
        self.session.add(member)
        await self.session.flush()
        return member
