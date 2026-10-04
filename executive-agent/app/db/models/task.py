"""Task extracted from an email or created by the user."""

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.constants import TaskStatus
from app.db.base import Base, UtcDateTime
from app.utils.time import utcnow


class Task(Base):
    """Actionable work item with an optional due time."""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    email_id: Mapped[int | None] = mapped_column(ForeignKey("emails.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    due_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default=TaskStatus.OPEN, index=True)
    snooze_until: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="email")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
