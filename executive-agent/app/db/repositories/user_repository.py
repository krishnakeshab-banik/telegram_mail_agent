"""SQL for the users table. This repository is not scoped to a mailbox."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User


class UserRepository:
    """Persistence for accounts. It never reads mail or other user-owned rows."""

    def __init__(self, session: AsyncSession) -> None:
        """Store the session."""
        self.session = session

    async def get(self, user_id: int) -> User | None:
        """Return one account by primary key."""
        return await self.session.get(User, user_id)

    async def get_by_telegram(self, telegram_user_id: int) -> User | None:
        """Return the account linked to a Telegram user."""
        statement = select(User).where(User.telegram_user_id == telegram_user_id)
        return await self.session.scalar(statement)

    async def find_by_google_email(self, email: str) -> User | None:
        """Return the account already linked to a Google mailbox."""
        address = email.strip().lower()
        if not address:
            return None
        statement = select(User).where(User.google_email == address)
        return await self.session.scalar(statement)

    async def admin_chat_ids(self, telegram_ids: frozenset[int]) -> list[int]:
        """Return chat ids for admins who have talked to the bot."""
        statement = select(User).where(User.telegram_chat_id.is_not(None))
        rows = list(await self.session.scalars(statement))
        chats: list[int] = []
        for user in rows:
            marked = user.is_admin or user.telegram_user_id in telegram_ids
            if marked and user.telegram_chat_id is not None:
                chats.append(user.telegram_chat_id)
        return chats

    async def count(self) -> int:
        """Return how many accounts exist."""
        statement = select(func.count()).select_from(User)
        return int(await self.session.scalar(statement) or 0)

    async def add(self, user: User) -> User:
        """Insert an account."""
        self.session.add(user)
        await self.session.flush()
        return user
