"""One-shot connectivity checks reported to Telegram."""

from collections.abc import Awaitable, Callable
from datetime import timedelta

from pydantic import BaseModel

from app.bot import formatters
from app.exceptions import ExecutiveAgentError
from app.services.container import Container
from app.utils.logging import get_logger
from app.utils.time import utcnow

logger = get_logger(__name__)


class _Ping(BaseModel):
    """Tiny schema for the startup Gemini call."""

    ok: bool = True


async def run_startup_checks(container: Container) -> None:
    """Check Gemini, Gmail, and Calendar, then tell the owner the result."""
    lines = [
        await _safe("Gemini", lambda: _gemini(container)),
        await _safe("Gmail", lambda: _gmail(container)),
        await _safe("Calendar", lambda: _calendar(container)),
    ]
    text = "Startup check\n" + "\n".join(lines)
    logger.info("startup_check", result=text.replace("\n", " | "))
    chat_id = await container.preferences.chat_id()
    if chat_id is None:
        return
    await container.sender.send_text(chat_id, formatters.plain(text))


async def _safe(name: str, call: Callable[[], Awaitable[str]]) -> str:
    try:
        detail = await call()
    except ExecutiveAgentError as exc:
        return f"{name}: fail — {exc}"
    except Exception as exc:
        logger.warning("startup_check_failed", check=name, error_type=type(exc).__name__)
        return f"{name}: fail — {type(exc).__name__}"
    return f"{name}: pass — {detail}"


async def _gemini(container: Container) -> str:
    if container.settings.app_mode == "demo" or not container.gemini.enabled:
        return "skipped in demo or without a key"
    await container.gemini.generate_json(
        model=container.settings.gemini_model_fast,
        system_prompt="Return JSON only.",
        user_prompt="Set ok to true.",
        schema=_Ping,
    )
    return container.settings.gemini_model_fast


async def _gmail(container: Container) -> str:
    email, _history = await container.sync._mailbox.get_profile()
    return email or "profile ok"


async def _calendar(container: Container) -> str:
    start = utcnow()
    events = await container.calendar._calendar.list_events(start, start + timedelta(hours=1))
    return f"{len(events)} events in the next hour"
