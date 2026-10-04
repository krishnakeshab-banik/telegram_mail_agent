"""Shared async HTTP helpers for Google REST APIs."""

from typing import Any

import httpx

from app.exceptions import AuthExpiredError, CalendarApiError, GmailApiError, QuotaExceededError
from app.utils.rate_limit import AsyncRateLimiter
from app.utils.retry import async_retry


class GoogleHttp:
    """JSON client that maps status codes onto application errors."""

    def __init__(
        self, *, requests_per_minute: int, error_type: type[GmailApiError] | type[CalendarApiError]
    ) -> None:
        """Store the rate limit and the error class for this API.

        Args:
            requests_per_minute: Local request budget.
            error_type: Exception raised for unexpected statuses.
        """
        self._limiter = AsyncRateLimiter(requests_per_minute)
        self._error_type = error_type
        self._client = httpx.AsyncClient(timeout=30)

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    @async_retry()
    async def request(
        self,
        method: str,
        url: str,
        *,
        token: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send one authorized JSON request.

        Args:
            method: HTTP method.
            url: Absolute URL.
            token: Bearer token.
            params: Query parameters.
            json_body: JSON body.

        Returns:
            Parsed JSON object, or an empty object when the body is empty.
        """
        await self._limiter.wait()
        response = await self._client.request(
            method,
            url,
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            json=json_body,
        )
        return self._decode(response)

    @async_retry()
    async def request_bytes(self, url: str, *, token: str) -> bytes:
        """Download bytes from an authorized URL.

        Args:
            url: Absolute URL.
            token: Bearer token.

        Returns:
            Response body.
        """
        await self._limiter.wait()
        response = await self._client.get(url, headers={"Authorization": f"Bearer {token}"})
        if response.status_code == 401:
            raise AuthExpiredError("Google rejected the access token.")
        if response.status_code == 429:
            raise QuotaExceededError("Google API quota exceeded.")
        if response.status_code >= 400:
            raise self._error_type("Google download failed.", response.status_code)
        return response.content

    def _decode(self, response: httpx.Response) -> dict[str, Any]:
        if response.status_code == 401:
            raise AuthExpiredError("Google rejected the access token.")
        if response.status_code == 429:
            raise QuotaExceededError("Google API quota exceeded.")
        if response.status_code >= 400:
            raise self._error_type("Google API request failed.", response.status_code)
        if not response.content:
            return {}
        payload = response.json()
        if isinstance(payload, dict):
            return payload
        raise self._error_type("Google API returned a non-object response.", response.status_code)
