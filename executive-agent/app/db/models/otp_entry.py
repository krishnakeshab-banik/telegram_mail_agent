"""Masked one-time code stored apart from the alert stream."""

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UtcDateTime
from app.db.models.owned import OwnedMixin
from app.utils.time import utcnow


class OtpEntry(OwnedMixin, Base):
    """Encrypted OTP. The Telegram view only shows a mask until reveal."""

    __tablename__ = "otp_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    email_id: Mapped[int] = mapped_column(ForeignKey("emails.id"), unique=True, index=True)
    sender: Mapped[str] = mapped_column(String(320), default="")
    masked_code: Mapped[str] = mapped_column(String(32), default="")
    encrypted_code: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
