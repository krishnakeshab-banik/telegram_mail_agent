"""Process-local rate limiter for upstream APIs."""

import asyncio


class AsyncRateLimiter:
    """Spaces calls so a client stays under a per-minute budget."""

    def __init__(self, requests_per_minute: int) -> None:
        """Create a limiter.

        Args:
            requests_per_minute: Maximum calls allowed in a rolling minute.
        """
        self._interval = 60 / max(requests_per_minute, 1)
        self._lock = asyncio.Lock()
        self._next_allowed = 0.0

    async def wait(self) -> None:
        """Sleep until the next call is allowed."""
        async with self._lock:
            loop = asyncio.get_running_loop()
            delay = self._next_allowed - loop.time()
            if delay > 0:
                await asyncio.sleep(delay)
            self._next_allowed = loop.time() + self._interval
