"""Download, parse, and summarize attachments with size and type limits."""

import json
import tempfile
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.schemas import AttachmentSummarySchema
from app.ai.summarizer import Summarizer
from app.db.base import session_scope
from app.db.repositories.attachment_repository import AttachmentRepository
from app.db.repositories.email_repository import EmailRepository
from app.exceptions import AttachmentError, GmailApiError
from app.google.gmail_client import MailboxClient
from app.services.attachment_parse import extract_text
from app.utils.logging import get_logger
from app.utils.time import utcnow

logger = get_logger(__name__)

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv",
    "text/plain",
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
}
_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


class AttachmentService:
    """Summarize new attachments and store the result on the email record."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        mailbox: MailboxClient,
        summarizer: Summarizer,
        *,
        max_bytes: int,
    ) -> None:
        """Store collaborators and the size limit.

        Args:
            session_factory: Database session factory.
            mailbox: Source of attachment bytes.
            summarizer: Model used for summaries and scanned files.
            max_bytes: Maximum download size.
        """
        self._sessions = session_factory
        self._mailbox = mailbox
        self._summarizer = summarizer
        self._max_bytes = max_bytes

    async def process_email(self, email_id: int) -> int:
        """Summarize attachments for one email that have not been processed.

        Args:
            email_id: Local email id.

        Returns:
            Number of attachments summarized.
        """
        async with session_scope(self._sessions) as session:
            rows = await AttachmentRepository(session).list_for_email(email_id)
            message = await EmailRepository(session).get(email_id)
            pending = [
                (row.id, row.gmail_attachment_id, row.filename, row.mime_type, row.size_bytes)
                for row in rows
                if row.processed_at is None
            ]
            gmail_message_id = message.gmail_message_id if message else ""
        summarized = 0
        for attachment_id, remote_id, filename, mime_type, size_bytes in pending:
            await self._process_one(
                attachment_id, gmail_message_id, remote_id, filename, mime_type, size_bytes
            )
            summarized += 1
        return summarized

    async def _process_one(
        self,
        attachment_id: int,
        gmail_message_id: str,
        remote_id: str,
        filename: str,
        mime_type: str,
        size_bytes: int,
    ) -> None:
        if mime_type not in ALLOWED_MIME_TYPES:
            await self._store(attachment_id, "Skipped. File type is not allowed.", {})
            return
        if size_bytes > self._max_bytes:
            await self._store(attachment_id, "Skipped. File exceeds the size limit.", {})
            return
        try:
            data = await self._mailbox.get_attachment(gmail_message_id, remote_id)
        except (AttachmentError, GmailApiError) as exc:
            await self._store(attachment_id, "Attachment could not be downloaded.", {})
            logger.warning("attachment_download_failed", error_type=type(exc).__name__)
            return
        if len(data) > self._max_bytes:
            await self._store(attachment_id, "Skipped. File exceeds the size limit.", {})
            return
        try:
            summary = await self._summarize(filename, mime_type, data)
        except (AttachmentError, GmailApiError):
            await self._store(attachment_id, "Attachment could not be parsed.", {})
            return
        await self._store(attachment_id, summary.summary, summary.model_dump())
        logger.info("attachment_summarized", attachment_id=attachment_id, mime_type=mime_type)

    async def _summarize(
        self, filename: str, mime_type: str, data: bytes
    ) -> AttachmentSummarySchema:
        if mime_type in _IMAGE_TYPES:
            return await self._summarizer.summarize_attachment_media(filename, data, mime_type)
        text = _extract_safely(filename, mime_type, data)
        if mime_type == "application/pdf" and len(text.strip()) < 40:
            return await self._summarizer.summarize_attachment_media(filename, data, mime_type)
        return await self._summarizer.summarize_attachment_text(filename, text)

    async def _store(self, attachment_id: int, summary: str, extracted: dict[str, object]) -> None:
        async with session_scope(self._sessions) as session:
            attachment = await AttachmentRepository(session).get(attachment_id)
            if attachment is None:
                return
            attachment.summary = summary[:2000]
            attachment.extracted_json = json.dumps(extracted)
            attachment.processed_at = utcnow()


def _extract_safely(filename: str, mime_type: str, data: bytes) -> str:
    safe_name = Path(filename).name or "attachment"
    with tempfile.TemporaryDirectory(prefix="exec-agent-") as directory:
        path = Path(directory) / safe_name
        path.write_bytes(data)
        try:
            return extract_text(path, mime_type)
        except (OSError, ValueError) as exc:
            raise AttachmentError("The attachment could not be parsed.") from exc
