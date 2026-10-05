"""Shared repository helpers. User-owned queries cannot run without a user id."""

import json
from typing import Any, TypeVar, cast

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.user_context import peek_user_id
from app.exceptions import UnscopedQueryError

RowT = TypeVar("RowT")
StatementT = TypeVar("StatementT")


class SessionRepository:
    """A repository that is not tied to one mailbox, such as process errors."""

    def __init__(self, session: AsyncSession) -> None:
        """Store the session for one unit of work."""
        self.session = session


class BaseRepository(SessionRepository):
    """Repository whose every query is limited to one user."""

    def __init__(self, session: AsyncSession, user_id: int | None = None) -> None:
        """Store the session and the only user this instance may read or write.

        Args:
            session: Open async session.
            user_id: Account id. When omitted, the active user scope is required.
        """
        super().__init__(session)
        resolved = user_id if user_id is not None else peek_user_id()
        if resolved is None or resolved < 1:
            raise UnscopedQueryError("A user id is required for this query.")
        self.user_id = resolved

    def restrict(self, statement: StatementT, *models: type[Any]) -> StatementT:
        """Add a user_id filter for each model in the statement."""
        narrowed: Any = statement
        for model in models:
            narrowed = narrowed.where(model.user_id == self.user_id)
        return cast(StatementT, narrowed)

    def stamp(self, row: Any) -> None:
        """Assign the active user id before insert."""
        row.user_id = self.user_id

    def visible(self, row: RowT | None) -> RowT | None:
        """Hide a row that belongs to someone else."""
        if row is None or getattr(row, "user_id", None) != self.user_id:
            return None
        return row


def dumps(value: Any) -> str:
    """Serialize a value to compact JSON.

    Args:
        value: JSON-compatible object.

    Returns:
        JSON text.
    """
    return json.dumps(value, separators=(",", ":"), default=str)


def loads(value: str, fallback: Any) -> Any:
    """Parse JSON text, returning a fallback when it is empty or invalid.

    Args:
        value: Stored JSON text.
        fallback: Value used when parsing fails.

    Returns:
        Parsed object or the fallback.
    """
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def limit_query(statement: Select[Any], amount: int) -> Select[Any]:
    """Apply a positive limit to a statement.

    Args:
        statement: SQLAlchemy select.
        amount: Maximum rows.

    Returns:
        Limited statement.
    """
    return statement.limit(max(1, min(amount, 50)))
