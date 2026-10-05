"""One Telegram user and the settings that belong only to them."""

from datetime import datetime

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UtcDateTime
from app.utils.time import utcnow


class User(Base):
    """Account that connects one Telegram identity to one Google mailbox."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    telegram_username: Mapped[str] = mapped_column(String(64), default="")
    google_email: Mapped[str] = mapped_column(String(320), default="", index=True)
    telegram_chat_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    signup_step: Mapped[str] = mapped_column(String(16), default="", server_default="")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    quiet_start: Mapped[str] = mapped_column(String(5), default="22:00")
    quiet_end: Mapped[str] = mapped_column(String(5), default="07:00")
    reminder_offsets: Mapped[str] = mapped_column(String(64), default="360,30")
    briefing_hour: Mapped[int] = mapped_column(Integer, default=8)
    briefing_minute: Mapped[int] = mapped_column(Integer, default=0)
    wrapup_hour: Mapped[int] = mapped_column(Integer, default=20)
    wrapup_minute: Mapped[int] = mapped_column(Integer, default=0)
    tone: Mapped[str] = mapped_column(String(16), default="direct")
    importance_threshold: Mapped[int] = mapped_column(Integer, default=60)
    reminders_override_quiet: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    consented_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
