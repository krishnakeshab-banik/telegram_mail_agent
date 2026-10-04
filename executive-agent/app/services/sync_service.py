"""Incremental Gmail sync. Pub/Sub can replace the poll trigger later."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import session_scope
from app.db.models.attachment import Attachment
from app.db.models.email import EmailMessage
from app.db.repositories.attachment_repository import AttachmentRepository
from app.db.repositories.common import dumps
from app.db.repositories.email_repository import EmailRepository
from app.db.repositories.state_repository import SyncStateRepository
from app.exceptions import GmailApiError
from app.google.gmail_client import MailboxClient
from app.google.gmail_parser import parse_gmail_message
from app.utils.logging import get_logger
from app.utils.security import redact
from app.utils.time import utcnow

logger = get_logger(__name__)
_CATCH_UP_QUERY = "newer_than:7d"


class SyncService:
    """Pull new Gmail messages into the local database without processing them twice."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], mailbox: MailboxClient
    ) -> None:
        """Store collaborators.

        Args:
            session_factory: Database session factory.
            mailbox: Live or demo Gmail client.
        """
        self._sessions = session_factory
        self._mailbox = mailbox
        self._backfill_ran = False

    def consume_backfill(self) -> bool:
        """Return whether the last sync performed the first 7-day backfill."""
        ran = self._backfill_ran
        self._backfill_ran = False
        return ran

    async def sync_inbox(self) -> list[int]:
        """Fetch messages added since the stored history cursor.

        Returns:
            Local ids of messages inserted during this call.
        """
        try:
            identifiers, history_id, mailbox, backfill = await self._remote_ids(self._mailbox)
        except GmailApiError as exc:
            await self._record_error(redact(str(exc)))
            raise
        created: list[int] = []
        for gmail_id in identifiers:
            local_id = await self._insert_if_new(gmail_id, self._mailbox)
            if local_id is not None:
                created.append(local_id)
        await self._save_cursor(history_id, mailbox, "", backfill_done=backfill or None)
        if backfill:
            self._backfill_ran = True
        logger.info("gmail_sync_completed", inserted=len(created), history_id=history_id)
        return created

    async def import_account(
        self,
        mailbox: MailboxClient,
        *,
        history_id: str,
        backfill_done: bool,
    ) -> tuple[list[int], str, bool]:
        """Import one additional mailbox without moving the primary cursor.

        Args:
            mailbox: Client already authorized for that account.
            history_id: Stored history cursor, or empty when this is the first pull.
            backfill_done: Whether the 7-day backfill already ran.

        Returns:
            Inserted local ids, the new history id, and whether backfill is now done.
        """
        identifiers, new_history, _mailbox, backfill = await self._remote_ids(
            mailbox, history_id=history_id, backfill_done=backfill_done
        )
        created: list[int] = []
        for gmail_id in identifiers:
            local_id = await self._insert_if_new(gmail_id, mailbox)
            if local_id is not None:
                created.append(local_id)
        return created, new_history, backfill_done or backfill

    async def _remote_ids(
        self,
        mailbox: MailboxClient,
        *,
        history_id: str | None = None,
        backfill_done: bool | None = None,
    ) -> tuple[list[str], str, str, bool]:
        if history_id is None or backfill_done is None:
            async with session_scope(self._sessions) as session:
                state = await SyncStateRepository(session).get_singleton()
                history_id = state.history_id
                backfill_done = state.backfill_done
        profile_email, profile_history = await mailbox.get_profile()
        if not backfill_done:
            identifiers = await mailbox.list_message_ids(_CATCH_UP_QUERY)
            return identifiers, profile_history, profile_email, True
        try:
            identifiers, latest = await mailbox.list_history_ids(history_id)
        except GmailApiError as exc:
            if exc.status_code != 404:
                raise
            identifiers = await mailbox.list_message_ids(_CATCH_UP_QUERY)
            latest = profile_history
        return identifiers, latest, profile_email, False

    async def _insert_if_new(self, gmail_id: str, mailbox: MailboxClient) -> int | None:
        async with session_scope(self._sessions) as session:
            if await EmailRepository(session).get_by_gmail_id(gmail_id) is not None:
                return None
        resource = await mailbox.get_message(gmail_id)
        parsed = parse_gmail_message(resource)
        if not parsed.gmail_message_id:
            return None
        async with session_scope(self._sessions) as session:
            emails = EmailRepository(session)
            if await emails.get_by_gmail_id(gmail_id) is not None:
                return None
            message = await emails.add(_to_row(parsed))
            attachments = AttachmentRepository(session)
            for item in parsed.attachments:
                await attachments.add(
                    Attachment(
                        email_id=message.id,
                        gmail_attachment_id=item.gmail_attachment_id,
                        filename=item.filename[:500],
                        mime_type=item.mime_type[:128],
                        size_bytes=item.size_bytes,
                    )
                )
            return message.id

    async def _save_cursor(
        self, history_id: str, mailbox: str, error: str, *, backfill_done: bool | None
    ) -> None:
        async with session_scope(self._sessions) as session:
            state = await SyncStateRepository(session).get_singleton()
            state.history_id = history_id or state.history_id
            state.mailbox_email = mailbox or state.mailbox_email
            state.last_sync_at = utcnow()
            state.last_error = error
            if backfill_done:
                state.backfill_done = True
            if error:
                state.error_count += 1
            state.updated_at = utcnow()

    async def _record_error(self, message: str) -> None:
        async with session_scope(self._sessions) as session:
            state = await SyncStateRepository(session).get_singleton()
            state.last_error = message[:400]
            state.error_count += 1
            state.updated_at = utcnow()


def _to_row(parsed: object) -> EmailMessage:
    from app.google.gmail_parser import ParsedEmail

    if not isinstance(parsed, ParsedEmail):
        raise TypeError("Expected a parsed email.")
    return EmailMessage(
        gmail_message_id=parsed.gmail_message_id,
        thread_id=parsed.thread_id,
        history_id=parsed.history_id,
        sender_email=parsed.sender_email,
        sender_name=parsed.sender_name,
        to_recipients=parsed.to_recipients,
        cc_recipients=parsed.cc_recipients,
        subject=parsed.subject,
        snippet=parsed.snippet,
        body_text=parsed.body_text,
        labels=dumps(parsed.labels),
        received_at=parsed.received_at,
        is_unread=parsed.is_unread,
        is_bulk=parsed.is_bulk,
        has_attachments=parsed.has_attachments,
        in_reply_to=parsed.in_reply_to,
        references_header=parsed.references_header,
        message_id_header=parsed.message_id_header,
        direction=parsed.direction,
    )
