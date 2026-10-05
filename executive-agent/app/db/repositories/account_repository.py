"""Delete every row that belongs to one account."""

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.models.user import User


def tables_with_user_id() -> list[str]:
    """Return every table whose rows are stamped with a user id."""
    names = [
        table.name
        for table in Base.metadata.sorted_tables
        if "user_id" in table.c and table.name != "users"
    ]
    return names


class AccountRepository:
    """Erase one account. It does not return message contents."""

    def __init__(self, session: AsyncSession) -> None:
        """Store the session."""
        self.session = session

    async def delete_user(self, user_id: int, telegram_user_id: int) -> None:
        """Remove the account and every row stamped with that user id."""
        del telegram_user_id
        for table in reversed(Base.metadata.sorted_tables):
            if "user_id" not in table.c or table.name == "users":
                continue
            await self.session.execute(delete(table).where(table.c.user_id == user_id))
        await self.session.execute(delete(User).where(User.id == user_id))
