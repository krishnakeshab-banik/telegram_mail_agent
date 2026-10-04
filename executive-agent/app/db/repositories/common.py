"""Shared repository helpers."""

import json
from typing import Any

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    """Holds the session used by a repository instance."""

    def __init__(self, session: AsyncSession) -> None:
        """Store the session for the lifetime of one unit of work.

        Args:
            session: Open async session.
        """
        self.session = session


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
