"""Read-only mailbox views for Telegram commands."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import session_scope
from app.db.repositories.analysis_repository import AnalysisRepository
from app.db.repositories.email_repository import EmailRepository
from app.services.preference_service import PreferenceService


class InboxService:
    """Lists used by /important, /unread, and /categories."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        preferences: PreferenceService,
    ) -> None:
        """Store collaborators.

        Args:
            session_factory: Database session factory.
            preferences: Importance threshold.
        """
        self._sessions = session_factory
        self._preferences = preferences

    async def important_lines(self) -> list[str]:
        """Return short lines for important mail."""
        threshold = (await self._preferences.get()).importance_threshold
        async with session_scope(self._sessions) as session:
            messages = await EmailRepository(session).list_important(threshold, limit=8)
            lines = []
            for message in messages:
                analysis = await AnalysisRepository(session).get_by_email(message.id)
                summary = analysis.summary if analysis else message.snippet
                lines.append(f"#{message.id} {message.sender_email}: {message.subject} — {summary}")
        return lines

    async def unread_lines(self) -> list[str]:
        """Return short lines for unread mail."""
        async with session_scope(self._sessions) as session:
            messages = await EmailRepository(session).list_unread(limit=8)
        return [f"#{message.id} {message.sender_email}: {message.subject}" for message in messages]

    async def subject_of(self, email_id: int) -> str:
        """Return an email subject, or a fallback title."""
        async with session_scope(self._sessions) as session:
            message = await EmailRepository(session).get(email_id)
        return message.subject if message else "Follow up"

    async def sender_of(self, email_id: int) -> str:
        """Return the sender address for an email."""
        async with session_scope(self._sessions) as session:
            message = await EmailRepository(session).get(email_id)
        return message.sender_email if message else ""

    async def category_counts(self) -> dict[str, int]:
        """Return analyzed message counts by category."""
        async with session_scope(self._sessions) as session:
            return await AnalysisRepository(session).category_counts()
