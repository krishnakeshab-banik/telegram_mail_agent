"""Structured logging with secret and email redaction."""

import logging
import sys
from pathlib import Path
from typing import Any

import structlog

from app.utils.activity_log import configure_activity_log, get_activity_log
from app.utils.security import redact


def _redact_processor(
    _logger: Any,
    _method: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """Redact string values in a structured log event."""
    for key, value in list(event_dict.items()):
        if isinstance(value, str):
            event_dict[key] = redact(value)
    return event_dict


def configure_logging(level: str, *, json_output: bool, activity_path: Path | None = None) -> None:
    """Configure structlog and the standard library once at startup.

    Args:
        level: Log level name such as INFO.
        json_output: Emit JSON lines when True, console output otherwise.
        activity_path: Optional JSONL file for the operations console.
    """
    configure_activity_log(activity_path)
    renderer: structlog.types.Processor
    if json_output:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _redact_processor,
            _capture_processor,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.INFO)


def _capture_processor(
    _logger: Any,
    _method: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """Copy a redacted event into the operations log."""
    safe: dict[str, Any] = {}
    for key, value in event_dict.items():
        if key in {"exc_info"} or str(key).startswith("_"):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[str(key)] = value
        else:
            safe[str(key)] = str(value)[:180]
    get_activity_log().add(safe)
    return event_dict


def get_logger(name: str) -> Any:
    """Return a named structured logger.

    Args:
        name: Module name, usually __name__.

    Returns:
        Bound structlog logger.
    """
    return structlog.get_logger(name)
