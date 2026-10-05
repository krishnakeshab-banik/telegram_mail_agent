"""Virtual mail folder."""

from datetime import datetime

from sqlalchemy import Boolean, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UtcDateTime
from app.db.models.owned import OwnedMixin
from app.utils.time import utcnow


class Folder(OwnedMixin, Base):
    """A named view over stored mail. Gmail labels are not changed here."""

    __tablename__ = "folders"
    __table_args__ = (UniqueConstraint("user_id", "slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(80))
    notify_mode: Mapped[str] = mapped_column(String(16), default="digest")
    rule_json: Mapped[str] = mapped_column(Text, default="")
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
