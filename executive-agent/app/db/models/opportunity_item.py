"""Structured record for a job, hackathon, event, or scholarship."""

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UtcDateTime
from app.db.models.owned import OwnedMixin
from app.utils.time import utcnow


class OpportunityItem(OwnedMixin, Base):
    """Fields extracted for an opportunity folder."""

    __tablename__ = "opportunity_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    email_id: Mapped[int] = mapped_column(ForeignKey("emails.id"), index=True)
    folder_slug: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(Text, default="")
    organization: Mapped[str] = mapped_column(String(200), default="")
    deadline_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    link: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="new", index=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
