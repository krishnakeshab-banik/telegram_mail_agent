"""Async retry with exponential backoff."""

import asyncio
import functools
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

from app.exceptions import QuotaExceededError
from app.utils.logging import get_logger

P = ParamSpec("P")
R = TypeVar("R")
logger = get_logger(__name__)


def async_retry(
    *,
    attempts: int = 4,
    base_seconds: float = 0.5,
    retry_on: tuple[type[Exception], ...] = (QuotaExceededError, TimeoutError, ConnectionError),
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Retry an async function when a transient error is raised.

    Args:
        attempts: Maximum attempts including the first call.
        base_seconds: Initial delay. Later delays double.
        retry_on: Exception types that should be retried.

    Returns:
        Decorator preserving the wrapped signature.
    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            last_error: Exception | None = None
            for attempt in range(1, attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except retry_on as exc:
                    last_error = exc
                    if attempt == attempts:
                        break
                    delay = base_seconds * (2 ** (attempt - 1))
                    logger.warning(
                        "retrying_call",
                        function=func.__name__,
                        attempt=attempt,
                        delay_seconds=delay,
                        error_type=type(exc).__name__,
                    )
                    await asyncio.sleep(delay)
            assert last_error is not None
            raise last_error

        return wrapper

    return decorator
