"""Recent Telegram turns used as Q&A context."""

from datetime import datetime

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UtcDateTime
from app.db.models.owned import OwnedMixin
from app.utils.time import utcnow


class ConversationTurn(OwnedMixin, Base):
    """One user or assistant message in the natural-language conversation."""

    __tablename__ = "conversation_turns"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, index=True)
