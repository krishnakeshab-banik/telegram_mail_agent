"""Single Gemini wrapper with retries, rate limits, and JSON schema output."""

import json
from typing import Any

from pydantic import BaseModel

from app.exceptions import GeminiError, QuotaExceededError
from app.utils.logging import get_logger
from app.utils.rate_limit import AsyncRateLimiter
from app.utils.retry import async_retry
from app.utils.security import redact

logger = get_logger(__name__)
_FALLBACK_MODELS = ("gemini-3.5-flash", "gemini-flash-latest", "gemini-3.1-flash-lite")


class GeminiClient:
    """Async Gemini client. Callers pass prompts; this class never logs them."""

    def __init__(self, api_key: str, *, requests_per_minute: int) -> None:
        """Create a client.

        Args:
            api_key: Gemini API key. Empty disables live calls.
            requests_per_minute: Local rate limit shared by every method.
        """
        self._api_key = api_key
        self._limiter = AsyncRateLimiter(requests_per_minute)
        self._client: Any = None

    @property
    def enabled(self) -> bool:
        """Return whether a live API key is configured."""
        return bool(self._api_key)

    def _sdk(self) -> Any:
        """Lazily construct the official async-capable client."""
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise GeminiError("GEMINI_API_KEY is not configured.")
        try:
            from google import genai
        except ImportError as exc:
            raise GeminiError("The google-genai package is not installed.") from exc
        self._client = genai.Client(api_key=self._api_key)
        return self._client

    async def generate_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        schema: type[BaseModel],
    ) -> dict[str, Any]:
        """Generate a JSON object validated later by the caller.

        Args:
            model: Gemini model name from settings.
            system_prompt: Trusted instruction text.
            user_prompt: User or wrapped-untrusted content.
            schema: Pydantic model whose schema is sent to Gemini.

        Returns:
            Parsed JSON object.
        """
        last_error: Exception | None = None
        for candidate in fallback_models(model):
            try:
                text = await self._generate(
                    model=candidate,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    schema=schema,
                )
                return _parse_json_object(text)
            except QuotaExceededError as exc:
                last_error = exc
                logger.warning("gemini_model_fallback", model=candidate)
        if last_error is not None:
            raise last_error
        raise GeminiError("Gemini request failed.")

    @async_retry()
    async def generate_with_media(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        media: bytes,
        mime_type: str,
        schema: type[BaseModel],
    ) -> dict[str, Any]:
        """Generate JSON from a prompt plus one image or PDF payload.

        Args:
            model: Gemini model name.
            system_prompt: Trusted instruction text.
            user_prompt: Wrapped untrusted instructions for the document.
            media: Raw file bytes.
            mime_type: IANA media type.
            schema: Expected JSON shape.

        Returns:
            Parsed JSON object.
        """
        from google.genai import types

        part = types.Part.from_bytes(data=media, mime_type=mime_type)
        text = await self._generate(
            model=model,
            system_prompt=system_prompt,
            user_prompt=[part, user_prompt],
            schema=schema,
        )
        return _parse_json_object(text)

    async def _generate(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str | list[Any],
        schema: type[BaseModel],
    ) -> str:
        from google.genai import types
        from google.genai.errors import APIError

        await self._limiter.wait()
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.2,
            response_mime_type="application/json",
            response_schema=schema,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        try:
            response = await self._sdk().aio.models.generate_content(
                model=model,
                contents=user_prompt,
                config=config,
            )
        except APIError as exc:
            _raise_api_error(exc)
        text = getattr(response, "text", None) or ""
        if not text.strip():
            raise GeminiError("Gemini returned an empty response.")
        logger.info("gemini_json_completed", model=model, schema=schema.__name__)
        return text


def fallback_models(preferred: str) -> tuple[str, ...]:
    """Return the preferred model followed by known available alternates.

    Args:
        preferred: Model name from settings.

    Returns:
        Unique model names to try in order.
    """
    ordered = [preferred, *_FALLBACK_MODELS]
    unique: list[str] = []
    for name in ordered:
        if name and name not in unique:
            unique.append(name)
    return tuple(unique)


def _raise_api_error(exc: Exception) -> None:
    code = getattr(exc, "code", None)
    detail = redact(str(getattr(exc, "message", "") or "")).replace("\n", " ")[:240]
    logger.warning("gemini_request_failed", code=code, detail=detail)
    if code in {429, 503}:
        raise QuotaExceededError(f"Gemini quota exceeded ({code}). {detail}".strip()) from exc
    raise GeminiError(f"Gemini request failed ({code}). {detail}".strip()) from exc


def _parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        cleaned = cleaned.rsplit("```", 1)[0]
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise GeminiError("Gemini returned invalid JSON.") from exc
    if not isinstance(parsed, dict):
        raise GeminiError("Gemini JSON was not an object.")
    return parsed
