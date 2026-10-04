"""A Telegram user who connected a Google account."""

from datetime import datetime

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UtcDateTime
from app.utils.time import utcnow


class Member(Base):
    """Signup record. Tokens are encrypted and belong to one Telegram user."""

    __tablename__ = "members"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    chat_id: Mapped[int] = mapped_column(Integer, default=0)
    account_email: Mapped[str] = mapped_column(String(320), default="")
    encrypted_access_token: Mapped[str] = mapped_column(Text, default="")
    encrypted_refresh_token: Mapped[str] = mapped_column(Text, default="")
    token_expiry: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    history_id: Mapped[str] = mapped_column(String(64), default="")
    backfill_done: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
