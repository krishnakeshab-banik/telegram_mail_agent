"""Thread summaries built from locally stored messages."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.schemas import ThreadSummarySchema
from app.ai.summarizer import Summarizer
from app.db.base import session_scope
from app.db.repositories.email_repository import EmailRepository
from app.exceptions import RecordNotFoundError


class ThreadService:
    """Load a thread and ask the summarizer for a compact view."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], summarizer: Summarizer
    ) -> None:
        """Store collaborators.

        Args:
            session_factory: Database session factory.
            summarizer: Thread summary model.
        """
        self._sessions = session_factory
        self._summarizer = summarizer

    async def summarize(self, email_id: int) -> ThreadSummarySchema:
        """Summarize the thread that contains an email.

        Args:
            email_id: Any message in the thread.

        Returns:
            Validated thread summary.
        """
        async with session_scope(self._sessions) as session:
            message = await EmailRepository(session).get(email_id)
            if message is None:
                raise RecordNotFoundError("That email is not stored.")
            thread = await EmailRepository(session).list_thread(message.thread_id)
        blocks = [
            f"From: {item.sender_name} <{item.sender_email}>\nSubject: {item.subject}\n{item.body_text[:2000]}"
            for item in thread
        ]
        return await self._summarizer.summarize_thread(blocks or [message.body_text])
