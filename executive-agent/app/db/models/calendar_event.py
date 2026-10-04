"""Local record of a detected or created calendar event."""

from datetime import datetime

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.constants import CalendarEventStatus
from app.db.base import Base, UtcDateTime
from app.utils.time import utcnow


class CalendarEvent(Base):
    """Meeting proposal or a Google Calendar event created by the agent."""

    __tablename__ = "calendar_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    email_id: Mapped[int | None] = mapped_column(ForeignKey("emails.id"), nullable=True, index=True)
    google_event_id: Mapped[str] = mapped_column(String(256), default="")
    title: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    start_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True, index=True)
    end_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    timezone_name: Mapped[str] = mapped_column(String(64), default="UTC")
    location: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str] = mapped_column(Text, default="")
    attendees: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(
        String(16), default=CalendarEventStatus.PROPOSED, index=True
    )
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
