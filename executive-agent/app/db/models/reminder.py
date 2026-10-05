"""Scheduled Telegram reminder."""

from datetime import datetime

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.constants import ReminderStatus
from app.db.base import Base, UtcDateTime
from app.db.models.owned import OwnedMixin
from app.utils.time import utcnow


class Reminder(OwnedMixin, Base):
    """A future Telegram ping for a task, deadline, or meeting."""

    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True)
    target_type: Mapped[str] = mapped_column(String(32), index=True)
    target_id: Mapped[int] = mapped_column(Integer, index=True)
    fire_at: Mapped[datetime] = mapped_column(UtcDateTime(), index=True)
    lead_minutes: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default=ReminderStatus.PENDING, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
