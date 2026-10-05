"""Membership of one email in one folder."""

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UtcDateTime
from app.db.models.owned import OwnedMixin
from app.utils.time import utcnow


class EmailFolderLink(OwnedMixin, Base):
    """One email can sit in several folders. One link is primary."""

    __tablename__ = "email_folder_links"
    __table_args__ = (UniqueConstraint("email_id", "folder_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    email_id: Mapped[int] = mapped_column(ForeignKey("emails.id"), index=True)
    folder_id: Mapped[int] = mapped_column(ForeignKey("folders.id"), index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="new")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
