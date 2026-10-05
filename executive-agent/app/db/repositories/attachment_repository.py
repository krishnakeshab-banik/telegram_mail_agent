"""SQL for attachments."""

from sqlalchemy import select

from app.db.models.attachment import Attachment
from app.db.repositories.common import BaseRepository


class AttachmentRepository(BaseRepository):
    """Persistence for attachment metadata and summaries."""

    async def get(self, attachment_id: int) -> Attachment | None:
        """Return one attachment."""
        return self.visible(await self.session.get(Attachment, attachment_id))

    async def add(self, attachment: Attachment) -> Attachment:
        """Insert an attachment row."""
        self.stamp(attachment)
        self.session.add(attachment)
        await self.session.flush()
        return attachment

    async def list_for_email(self, email_id: int) -> list[Attachment]:
        """Return attachments stored for one message."""
        statement = self.restrict(
            select(Attachment).where(Attachment.email_id == email_id), Attachment
        )
        return list(await self.session.scalars(statement))
