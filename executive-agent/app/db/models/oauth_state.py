"""Single-use Google OAuth state for the web callback."""

from datetime import datetime

from sqlalchemy import Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UtcDateTime
from app.db.models.owned import OwnedMixin
from app.utils.time import utcnow


class OAuthState(OwnedMixin, Base):
    """One Connect Google attempt. The nonce cannot be spent twice."""

    __tablename__ = "oauth_states"
    __table_args__ = (UniqueConstraint("nonce"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    nonce: Mapped[str] = mapped_column(String(64), index=True)
    encrypted_verifier: Mapped[str] = mapped_column(Text, default="")
    telegram_chat_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime(), index=True)
    used_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
