"""Classifier output for one email."""

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UtcDateTime
from app.db.models.owned import OwnedMixin
from app.utils.time import utcnow


class EmailAnalysis(OwnedMixin, Base):
    """Structured understanding of a single message."""

    __tablename__ = "email_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    email_id: Mapped[int] = mapped_column(ForeignKey("emails.id"), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    importance_score: Mapped[int] = mapped_column(Integer, default=0)
    urgency: Mapped[str] = mapped_column(String(16), default="low")
    requires_reply: Mapped[bool] = mapped_column(Boolean, default=False)
    summary: Mapped[str] = mapped_column(Text, default="")
    sentiment: Mapped[str] = mapped_column(String(64), default="")
    action_items_json: Mapped[str] = mapped_column(Text, default="[]")
    deadlines_json: Mapped[str] = mapped_column(Text, default="[]")
    meeting_json: Mapped[str] = mapped_column(Text, default="")
    outbound_promise: Mapped[str] = mapped_column(Text, default="")
    promise_due: Mapped[str] = mapped_column(String(64), default="")
    model_name: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
