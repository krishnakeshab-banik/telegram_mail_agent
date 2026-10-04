"""User confirmation required before a mutating action."""

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.constants import ApprovalStatus
from app.db.base import Base, UtcDateTime
from app.utils.time import utcnow


class Approval(Base):
    """Pending or resolved confirmation for an outbound action."""

    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    action_type: Mapped[str] = mapped_column(String(32), index=True)
    payload_encrypted: Mapped[str] = mapped_column(Text, default="")
    payload_hash: Mapped[str] = mapped_column(String(64), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default=ApprovalStatus.PENDING, index=True)
    source_email_id: Mapped[int | None] = mapped_column(ForeignKey("emails.id"), nullable=True)
    telegram_user_id: Mapped[int | None] = mapped_column(nullable=True)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime(), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    result_summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
