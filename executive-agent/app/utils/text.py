"""Text cleanup helpers used by parsers and formatters."""

import re

_WHITESPACE = re.compile(r"[ \t]+")
_BLANK_LINES = re.compile(r"\n{3,}")


def collapse_whitespace(value: str) -> str:
    """Collapse runs of spaces and extra blank lines.

    Args:
        value: Raw text.

    Returns:
        Cleaned text.
    """
    lines = [_WHITESPACE.sub(" ", line).strip() for line in value.replace("\r\n", "\n").split("\n")]
    return _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


def truncate(value: str, limit: int) -> str:
    """Truncate text to a character limit, keeping whole words when possible.

    Args:
        value: Source text.
        limit: Maximum characters.

    Returns:
        Truncated text with an ellipsis when shortened.
    """
    cleaned = value.strip()
    if len(cleaned) <= limit:
        return cleaned
    shortened = cleaned[: limit - 1].rsplit(" ", 1)[0]
    return f"{shortened}…"


def excerpt(value: str, limit: int = 280) -> str:
    """Return a single-line excerpt.

    Args:
        value: Source text.
        limit: Maximum characters.

    Returns:
        One-line excerpt.
    """
    single = collapse_whitespace(value).replace("\n", " ")
    return truncate(single, limit)


def clip_lines(value: str, max_lines: int) -> str:
    """Keep the first non-empty lines of a block.

    Args:
        value: Source text.
        max_lines: Line budget.

    Returns:
        Joined lines.
    """
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    return "\n".join(lines[:max_lines])
