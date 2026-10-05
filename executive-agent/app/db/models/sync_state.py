"""Mailbox sync cursor."""

from datetime import datetime

from sqlalchemy import Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UtcDateTime
from app.db.models.owned import OwnedMixin
from app.utils.time import utcnow


class SyncState(OwnedMixin, Base):
    """Gmail history cursor and the last successful poll."""

    __tablename__ = "sync_states"
    __table_args__ = (UniqueConstraint("user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    mailbox_email: Mapped[str] = mapped_column(String(320), default="")
    history_id: Mapped[str] = mapped_column(String(64), default="")
    last_sync_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    backfill_done: Mapped[bool] = mapped_column(Boolean, default=False)
    last_gemini_error: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
