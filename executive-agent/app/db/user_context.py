"""The user a repository query is allowed to see. Unset means the query is refused."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

_CURRENT_USER: ContextVar[int | None] = ContextVar("current_user_id", default=None)


def peek_user_id() -> int | None:
    """Return the active user id, or None when no scope is set."""
    return _CURRENT_USER.get()


@contextmanager
def no_user_scope() -> Iterator[None]:
    """Clear the active user so a repository must be given an id explicitly."""
    token: Token[int | None] = _CURRENT_USER.set(None)
    try:
        yield
    finally:
        _CURRENT_USER.reset(token)


@contextmanager
def user_scope(user_id: int) -> Iterator[None]:
    """Limit repository queries to one user until the block exits.

    Args:
        user_id: Primary key of the user who owns the rows.
    """
    if user_id < 1:
        raise ValueError("A user scope requires a positive user id.")
    token: Token[int | None] = _CURRENT_USER.set(user_id)
    try:
        yield
    finally:
        _CURRENT_USER.reset(token)
