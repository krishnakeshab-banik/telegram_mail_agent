"""Singleton runtime flags such as pause and the last briefing date."""

from datetime import datetime

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UtcDateTime
from app.utils.time import utcnow


class AgentState(Base):
    """Process flags that must survive a restart."""

    __tablename__ = "agent_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    telegram_chat_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_briefing_on: Mapped[str] = mapped_column(String(10), default="")
    last_wrapup_on: Mapped[str] = mapped_column(String(10), default="")
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
