"""Account lookup. The original owner is always user 1."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.base import session_scope
from app.db.models.user import User
from app.db.repositories.user_repository import UserRepository
from app.utils.time import utcnow


class UserService:
    """Find accounts and make sure the migrated owner exists."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], settings: Settings
    ) -> None:
        """Store collaborators.

        Args:
            session_factory: Database session factory.
            settings: Supplies the original Telegram id and default preferences.
        """
        self._sessions = session_factory
        self._settings = settings

    async def ensure_owner(self) -> User:
        """Return user 1, creating or repairing the row from the original allowlist."""
        async with session_scope(self._sessions) as session:
            repo = UserRepository(session)
            allowed = sorted(self._settings.allowed_user_ids)
            telegram_id = allowed[0] if allowed else 0
            existing = await repo.get(1)
            if existing is None and telegram_id:
                existing = await repo.get_by_telegram(telegram_id)
            if existing is None:
                return await repo.add(self._new_owner(telegram_id or 1))
            if telegram_id and existing.telegram_user_id == 0:
                existing.telegram_user_id = telegram_id
            if existing.status == "pending":
                existing.status = "active"
            if existing.id == 1 or existing.telegram_user_id in self._settings.admin_ids:
                existing.is_admin = True
            return existing

    async def get(self, user_id: int) -> User | None:
        """Return one account."""
        async with session_scope(self._sessions) as session:
            return await UserRepository(session).get(user_id)

    async def remember_chat(self, user_id: int, chat_id: int) -> None:
        """Store the chat that should receive this account's messages."""
        async with session_scope(self._sessions) as session:
            user = await UserRepository(session).get(user_id)
            if user is not None:
                user.telegram_chat_id = chat_id

    async def by_telegram(self, telegram_user_id: int) -> User | None:
        """Return the account for a Telegram user, if one exists."""
        async with session_scope(self._sessions) as session:
            return await UserRepository(session).get_by_telegram(telegram_user_id)

    def _new_owner(self, telegram_id: int) -> User:
        settings = self._settings
        return User(
            id=1,
            telegram_user_id=telegram_id,
            timezone=settings.timezone,
            status="active",
            is_admin=True,
            quiet_start=settings.quiet_hours_start,
            quiet_end=settings.quiet_hours_end,
            importance_threshold=settings.importance_notify_threshold,
            briefing_hour=settings.briefing_hour,
            briefing_minute=settings.briefing_minute,
            wrapup_hour=settings.wrapup_hour,
            wrapup_minute=settings.wrapup_minute,
            consented_at=utcnow(),
        )
