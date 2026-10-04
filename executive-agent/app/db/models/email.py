"""Stored Gmail message."""

from datetime import datetime

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.constants import EmailDirection, NotificationStatus
from app.db.base import Base, UtcDateTime
from app.utils.time import utcnow


class EmailMessage(Base):
    """One Gmail message, processed at most once."""

    __tablename__ = "emails"

    id: Mapped[int] = mapped_column(primary_key=True)
    gmail_message_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    thread_id: Mapped[str] = mapped_column(String(64), index=True)
    history_id: Mapped[str] = mapped_column(String(64), default="")
    sender_email: Mapped[str] = mapped_column(String(320), index=True, default="")
    sender_name: Mapped[str] = mapped_column(String(256), default="")
    to_recipients: Mapped[str] = mapped_column(Text, default="")
    cc_recipients: Mapped[str] = mapped_column(Text, default="")
    subject: Mapped[str] = mapped_column(Text, default="")
    snippet: Mapped[str] = mapped_column(Text, default="")
    body_text: Mapped[str] = mapped_column(Text, default="")
    labels: Mapped[str] = mapped_column(Text, default="")
    received_at: Mapped[datetime] = mapped_column(UtcDateTime(), index=True, default=utcnow)
    is_unread: Mapped[bool] = mapped_column(Boolean, default=True)
    is_bulk: Mapped[bool] = mapped_column(Boolean, default=False)
    has_attachments: Mapped[bool] = mapped_column(Boolean, default=False)
    in_reply_to: Mapped[str] = mapped_column(Text, default="")
    references_header: Mapped[str] = mapped_column(Text, default="")
    message_id_header: Mapped[str] = mapped_column(String(512), default="")
    direction: Mapped[str] = mapped_column(String(16), default=EmailDirection.INBOUND)
    processed_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    notified_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    notification_status: Mapped[str] = mapped_column(String(16), default=NotificationStatus.NONE)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
