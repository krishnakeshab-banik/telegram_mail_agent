"""SQL for stored email messages."""

from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, or_, select

from app.constants import EmailDirection, NotificationStatus
from app.db.models.analysis import EmailAnalysis
from app.db.models.email import EmailMessage
from app.db.repositories.common import BaseRepository, limit_query


class EmailRepository(BaseRepository):
    """Persistence for Gmail messages mirrored locally."""

    async def get(self, email_id: int) -> EmailMessage | None:
        """Return one message by primary key."""
        return await self.session.get(EmailMessage, email_id)

    async def get_by_gmail_id(self, gmail_message_id: str) -> EmailMessage | None:
        """Return a message by its Gmail id."""
        statement = select(EmailMessage).where(EmailMessage.gmail_message_id == gmail_message_id)
        return await self.session.scalar(statement)

    async def add(self, message: EmailMessage) -> EmailMessage:
        """Insert a message and flush so its id is available."""
        self.session.add(message)
        await self.session.flush()
        return message

    async def list_unprocessed(self, limit: int = 20) -> list[EmailMessage]:
        """Return messages that do not yet have a finished pipeline run."""
        statement = (
            select(EmailMessage)
            .where(EmailMessage.processed_at.is_(None))
            .order_by(EmailMessage.received_at.asc())
            .limit(limit)
        )
        return list(await self.session.scalars(statement))

    async def count_unprocessed(self) -> int:
        """Count messages waiting for the pipeline."""
        statement = (
            select(func.count())
            .select_from(EmailMessage)
            .where(EmailMessage.processed_at.is_(None))
        )
        return int(await self.session.scalar(statement) or 0)

    async def list_thread(self, thread_id: str) -> list[EmailMessage]:
        """Return every stored message in a Gmail thread, oldest first."""
        statement = (
            select(EmailMessage)
            .where(EmailMessage.thread_id == thread_id)
            .order_by(EmailMessage.received_at.asc())
        )
        return list(await self.session.scalars(statement))

    async def list_by_notification_status(
        self,
        status: NotificationStatus,
        limit: int = 20,
    ) -> list[EmailMessage]:
        """Return processed messages in a notification state."""
        statement = (
            select(EmailMessage)
            .where(
                EmailMessage.notification_status == status,
                EmailMessage.processed_at.is_not(None),
            )
            .order_by(EmailMessage.received_at.asc())
            .limit(limit)
        )
        return list(await self.session.scalars(statement))

    async def claim_notification(self, email_id: int) -> bool:
        """Mark a message claimed so only one worker notifies it.

        Args:
            email_id: Local email id.

        Returns:
            True when this caller won the claim.
        """
        message = await self.get(email_id)
        if message is None:
            return False
        if message.notification_status not in {NotificationStatus.NONE, NotificationStatus.HELD}:
            return False
        message.notification_status = NotificationStatus.CLAIMED
        await self.session.flush()
        return True

    async def mark_notified(self, email_id: int, moment: datetime) -> None:
        """Record that a Telegram alert was delivered."""
        message = await self.get(email_id)
        if message is None:
            return
        message.notification_status = NotificationStatus.SENT
        message.notified_at = moment

    async def hold_notification(self, email_id: int) -> None:
        """Keep an alert until quiet hours end."""
        message = await self.get(email_id)
        if message is None:
            return
        message.notification_status = NotificationStatus.HELD

    async def skip_notification(self, email_id: int) -> None:
        """Record that an alert was intentionally not sent."""
        message = await self.get(email_id)
        if message is None:
            return
        message.notification_status = NotificationStatus.SKIPPED

    async def release_claim(self, email_id: int) -> None:
        """Return a claimed alert to the held queue after a send failure."""
        message = await self.get(email_id)
        if message is None:
            return
        if message.notification_status == NotificationStatus.CLAIMED:
            message.notification_status = NotificationStatus.HELD

    async def search(
        self,
        *,
        sender: str | None,
        keywords: list[str],
        category: str | None,
        min_importance: int | None,
        date_from: datetime | None,
        date_to: datetime | None,
        unread_only: bool,
        limit: int,
    ) -> list[EmailMessage]:
        """Search local messages using structured filters."""
        statement = self._search_statement(
            sender=sender,
            keywords=keywords,
            category=category,
            min_importance=min_importance,
            date_from=date_from,
            date_to=date_to,
            unread_only=unread_only,
        )
        return list(await self.session.scalars(limit_query(statement, limit)))

    async def count_received_since(self, moment: datetime) -> int:
        """Count inbound messages received at or after a moment."""
        statement = (
            select(func.count())
            .select_from(EmailMessage)
            .where(
                EmailMessage.received_at >= moment,
                EmailMessage.direction == EmailDirection.INBOUND,
            )
        )
        return int(await self.session.scalar(statement) or 0)

    async def count_important(self, threshold: int) -> int:
        """Count inbound messages at or above an importance threshold."""
        statement = (
            select(func.count())
            .select_from(EmailMessage)
            .join(EmailAnalysis, EmailAnalysis.email_id == EmailMessage.id)
            .where(
                EmailAnalysis.importance_score >= threshold,
                EmailMessage.direction == EmailDirection.INBOUND,
            )
        )
        return int(await self.session.scalar(statement) or 0)

    async def list_recent_inbound(self, limit: int = 8) -> list[EmailMessage]:
        """Return recent inbound mail that is not marked bulk."""
        statement = (
            select(EmailMessage)
            .where(
                EmailMessage.direction == EmailDirection.INBOUND,
                EmailMessage.is_bulk.is_(False),
            )
            .order_by(EmailMessage.received_at.desc())
        )
        return list(await self.session.scalars(limit_query(statement, limit)))

    async def list_important(self, threshold: int, limit: int = 5) -> list[EmailMessage]:
        """Return recent high-importance inbound mail."""
        statement = (
            select(EmailMessage)
            .join(EmailAnalysis, EmailAnalysis.email_id == EmailMessage.id)
            .where(
                EmailAnalysis.importance_score >= threshold,
                EmailMessage.direction == EmailDirection.INBOUND,
            )
            .order_by(EmailMessage.received_at.desc())
        )
        return list(await self.session.scalars(limit_query(statement, limit)))

    async def list_unread(self, limit: int = 10) -> list[EmailMessage]:
        """Return recent unread inbound mail."""
        statement = (
            select(EmailMessage)
            .where(
                EmailMessage.is_unread.is_(True), EmailMessage.direction == EmailDirection.INBOUND
            )
            .order_by(EmailMessage.received_at.desc())
        )
        return list(await self.session.scalars(limit_query(statement, limit)))

    def _search_statement(
        self,
        *,
        sender: str | None,
        keywords: list[str],
        category: str | None,
        min_importance: int | None,
        date_from: datetime | None,
        date_to: datetime | None,
        unread_only: bool,
    ) -> Select[Any]:
        statement = select(EmailMessage).order_by(EmailMessage.received_at.desc())
        if category or min_importance is not None:
            statement = statement.join(EmailAnalysis, EmailAnalysis.email_id == EmailMessage.id)
        if sender:
            like = f"%{sender.lower()}%"
            statement = statement.where(
                or_(
                    func.lower(EmailMessage.sender_email).like(like),
                    func.lower(EmailMessage.sender_name).like(like),
                )
            )
        for keyword in keywords:
            like = f"%{keyword.lower()}%"
            statement = statement.where(
                or_(
                    func.lower(EmailMessage.subject).like(like),
                    func.lower(EmailMessage.body_text).like(like),
                    func.lower(EmailMessage.snippet).like(like),
                )
            )
        if category:
            statement = statement.where(EmailAnalysis.category == category)
        if min_importance is not None:
            statement = statement.where(EmailAnalysis.importance_score >= min_importance)
        if date_from is not None:
            statement = statement.where(EmailMessage.received_at >= date_from)
        if date_to is not None:
            statement = statement.where(EmailMessage.received_at <= date_to)
        if unread_only:
            statement = statement.where(EmailMessage.is_unread.is_(True))
        return statement
