"""Encrypted Google OAuth token row."""

from datetime import datetime

from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UtcDateTime
from app.db.models.owned import OwnedMixin
from app.utils.time import utcnow


class OAuthToken(OwnedMixin, Base):
    """OAuth credentials encrypted at rest."""

    __tablename__ = "oauth_tokens"
    __table_args__ = (UniqueConstraint("user_id", "provider"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    account_email: Mapped[str] = mapped_column(String(320), default="")
    encrypted_access_token: Mapped[str] = mapped_column(Text, default="")
    encrypted_refresh_token: Mapped[str] = mapped_column(Text, default="")
    expiry: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    scopes: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
