"""Columns shared by every row that belongs to one user."""

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column


class OwnedMixin:
    """Require a user id on user-owned rows. Repositories filter on this column."""

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
