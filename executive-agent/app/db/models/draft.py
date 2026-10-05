"""Reply draft tied to an approval."""

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UtcDateTime
from app.db.models.owned import OwnedMixin
from app.utils.time import utcnow


class DraftReply(OwnedMixin, Base):
    """Generated reply, including whether the user edited it before sending."""

    __tablename__ = "draft_replies"

    id: Mapped[int] = mapped_column(primary_key=True)
    email_id: Mapped[int] = mapped_column(ForeignKey("emails.id"), index=True)
    approval_id: Mapped[int | None] = mapped_column(ForeignKey("approvals.id"), nullable=True)
    body: Mapped[str] = mapped_column(Text, default="")
    tone: Mapped[str] = mapped_column(String(32), default="direct")
    instruction: Mapped[str] = mapped_column(Text, default="")
    was_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    original_body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="preview")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
