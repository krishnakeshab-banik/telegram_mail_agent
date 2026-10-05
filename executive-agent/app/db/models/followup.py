"""Reply owed by the user, or a response the user is waiting on."""

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.constants import FollowUpDirection, FollowUpStatus
from app.db.base import Base, UtcDateTime
from app.db.models.owned import OwnedMixin
from app.utils.time import utcnow


class FollowUp(OwnedMixin, Base):
    """Open loop tracked until it is answered, dismissed, or snoozed."""

    __tablename__ = "followups"

    id: Mapped[int] = mapped_column(primary_key=True)
    email_id: Mapped[int | None] = mapped_column(ForeignKey("emails.id"), nullable=True, index=True)
    direction: Mapped[str] = mapped_column(
        String(32), default=FollowUpDirection.INBOUND_NEEDS_REPLY
    )
    counterpart_email: Mapped[str] = mapped_column(String(320), default="")
    subject: Mapped[str] = mapped_column(Text, default="")
    promise_text: Mapped[str] = mapped_column(Text, default="")
    due_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=FollowUpStatus.OPEN, index=True)
    last_nudged_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    snooze_until: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
