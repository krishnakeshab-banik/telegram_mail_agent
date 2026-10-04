"""Deadline extracted from an email."""

from datetime import datetime

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.constants import TaskStatus
from app.db.base import Base, UtcDateTime
from app.utils.time import utcnow


class Deadline(Base):
    """Time-bound commitment linked back to a source email."""

    __tablename__ = "deadlines"

    id: Mapped[int] = mapped_column(primary_key=True)
    email_id: Mapped[int | None] = mapped_column(ForeignKey("emails.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    due_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    status: Mapped[str] = mapped_column(String(16), default=TaskStatus.OPEN, index=True)
    snooze_until: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
