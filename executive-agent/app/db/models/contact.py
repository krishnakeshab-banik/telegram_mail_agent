"""Per-sender relationship profile."""

from datetime import datetime

from sqlalchemy import Boolean, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.constants import RelationshipType
from app.db.base import Base, UtcDateTime
from app.db.models.owned import OwnedMixin
from app.utils.time import utcnow


class Contact(OwnedMixin, Base):
    """Learned profile for one email address."""

    __tablename__ = "contacts"
    __table_args__ = (UniqueConstraint("user_id", "email"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    display_name: Mapped[str] = mapped_column(String(256), default="")
    relationship_type: Mapped[str] = mapped_column(String(32), default=RelationshipType.UNKNOWN)
    is_vip: Mapped[bool] = mapped_column(Boolean, default=False)
    is_muted: Mapped[bool] = mapped_column(Boolean, default=False)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    typical_topics: Mapped[str] = mapped_column(Text, default="")
    preferred_tone: Mapped[str] = mapped_column(String(32), default="")
    average_response_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    priority_weight: Mapped[float] = mapped_column(Float, default=1.0)
    last_interaction_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
