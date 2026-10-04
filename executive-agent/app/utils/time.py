"""Timezone helpers and relative date resolution."""

import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
_RELATIVE_AMOUNT = re.compile(
    r"\bin\s+(\d+)\s+(minute|minutes|hour|hours|day|days|week|weeks)\b",
    re.IGNORECASE,
)
_WEEKDAY_TIME = re.compile(
    r"\b(?:next\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
    r"(?:\s+at)?\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b",
    re.IGNORECASE,
)
_CLOCK = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.IGNORECASE)
_ISO_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}")


def utcnow() -> datetime:
    """Return the current timezone-aware UTC time."""
    return datetime.now(UTC)


def zone(name: str) -> ZoneInfo:
    """Return a timezone, falling back to UTC for unknown names.

    Args:
        name: IANA timezone name.

    Returns:
        ZoneInfo instance.
    """
    try:
        return ZoneInfo(name)
    except (KeyError, ValueError):
        return ZoneInfo("UTC")


def to_local(moment: datetime, timezone_name: str) -> datetime:
    """Convert an aware datetime into the user's timezone.

    Args:
        moment: Source datetime. Naive values are treated as UTC.
        timezone_name: IANA timezone name.

    Returns:
        Aware datetime in the requested zone.
    """
    aware = moment if moment.tzinfo else moment.replace(tzinfo=UTC)
    return aware.astimezone(zone(timezone_name))


def parse_clock(value: str) -> tuple[int, int] | None:
    """Parse an HH:MM 24-hour clock string.

    Args:
        value: Clock text such as 08:00.

    Returns:
        Hour and minute, or None when the text is not a clock.
    """
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", value.strip())
    if match is None:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return hour, minute


def in_quiet_hours(moment: datetime, timezone_name: str, start: str, end: str) -> bool:
    """Return whether a moment falls inside quiet hours.

    Args:
        moment: Instant to test.
        timezone_name: User timezone.
        start: Quiet start as HH:MM.
        end: Quiet end as HH:MM.

    Returns:
        True when notifications should be held.
    """
    start_clock = parse_clock(start)
    end_clock = parse_clock(end)
    if start_clock is None or end_clock is None:
        return False
    local = to_local(moment, timezone_name)
    current = local.hour * 60 + local.minute
    start_minutes = start_clock[0] * 60 + start_clock[1]
    end_minutes = end_clock[0] * 60 + end_clock[1]
    if start_minutes == end_minutes:
        return False
    if start_minutes < end_minutes:
        return start_minutes <= current < end_minutes
    return current >= start_minutes or current < end_minutes


def ensure_aware(value: datetime, timezone_name: str) -> datetime:
    """Attach a timezone to a naive datetime.

    Args:
        value: Datetime that may already be aware.
        timezone_name: Zone used for naive values.

    Returns:
        Aware datetime.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=zone(timezone_name))
    return value


def parse_iso(value: str, timezone_name: str) -> datetime | None:
    """Parse an ISO-8601 datetime.

    Args:
        value: ISO text, optionally without a timezone.
        timezone_name: Zone applied when the value is naive.

    Returns:
        Aware UTC datetime, or None when parsing fails.
    """
    text = value.strip().replace("Z", "+00:00")
    if not _ISO_PREFIX.match(text):
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return ensure_aware(parsed, timezone_name).astimezone(UTC)


def _next_weekday(local_now: datetime, weekday: int, *, force_next: bool) -> datetime:
    days_ahead = (weekday - local_now.weekday()) % 7
    if days_ahead == 0 and force_next:
        days_ahead = 7
    return local_now + timedelta(days=days_ahead)


def _apply_clock(local_day: datetime, hour: int, minute: int, meridiem: str | None) -> datetime:
    resolved_hour = hour
    if meridiem:
        resolved_hour = hour % 12
        if meridiem.lower() == "pm":
            resolved_hour += 12
    return local_day.replace(hour=resolved_hour, minute=minute, second=0, microsecond=0)


def describe_age(when: datetime, now: datetime) -> str:
    """Describe how long ago a message arrived."""
    moment = when if when.tzinfo else when.replace(tzinfo=UTC)
    current = now if now.tzinfo else now.replace(tzinfo=UTC)
    elapsed = current - moment
    if elapsed.total_seconds() < 3600:
        return "received just now"
    if elapsed < timedelta(hours=48):
        hours = max(1, int(elapsed.total_seconds() // 3600))
        return f"received {hours} hours ago"
    return f"received {elapsed.days} days ago"


def describe_due(due: datetime, now: datetime) -> str:
    """Describe a deadline relative to now, never calling the past 'hours left'.

    Args:
        due: Deadline instant.
        now: Current instant.

    Returns:
        Overdue, or a remaining-time phrase.
    """
    due_aware = due if due.tzinfo else due.replace(tzinfo=UTC)
    now_aware = now if now.tzinfo else now.replace(tzinfo=UTC)
    if due_aware <= now_aware:
        return "overdue"
    remaining = due_aware - now_aware
    if remaining < timedelta(hours=48):
        hours = max(1, int(remaining.total_seconds() // 3600))
        return f"{hours} hours left"
    return f"{remaining.days} days left"


def resolve_relative(phrase: str, *, now: datetime, timezone_name: str) -> datetime | None:
    """Resolve a human date phrase into an aware UTC datetime.

    Args:
        phrase: Text such as "tomorrow 3pm" or "next Tuesday 15:00".
        now: Current instant.
        timezone_name: User timezone used for calendar phrases.

    Returns:
        Aware UTC datetime, or None when the phrase is not recognized.
    """
    text = phrase.strip().lower()
    if not text:
        return None
    local_now = to_local(now, timezone_name)
    iso_value = parse_iso(phrase, timezone_name)
    if iso_value is not None and "next " not in text and "tomorrow" not in text:
        return iso_value
    amount = _RELATIVE_AMOUNT.search(text)
    if amount is not None:
        return _resolve_amount(local_now, int(amount.group(1)), amount.group(2))
    if text.startswith("tomorrow"):
        return _resolve_day_offset(local_now, text, days=1)
    if text.startswith("today"):
        return _resolve_day_offset(local_now, text, days=0)
    weekday_match = _WEEKDAY_TIME.search(text)
    if weekday_match is not None:
        return _resolve_weekday(local_now, text, weekday_match)
    return None


def _resolve_amount(local_now: datetime, count: int, unit: str) -> datetime:
    normalized = unit.lower()
    if normalized.startswith("minute"):
        delta = timedelta(minutes=count)
    elif normalized.startswith("hour"):
        delta = timedelta(hours=count)
    elif normalized.startswith("week"):
        delta = timedelta(weeks=count)
    else:
        delta = timedelta(days=count)
    return (local_now + delta).astimezone(UTC)


def _resolve_day_offset(local_now: datetime, text: str, *, days: int) -> datetime:
    target = (local_now + timedelta(days=days)).replace(second=0, microsecond=0)
    clock = _CLOCK.search(text)
    if clock is None:
        target = target.replace(hour=9, minute=0)
    else:
        target = _apply_clock(target, int(clock.group(1)), int(clock.group(2) or 0), clock.group(3))
    return target.astimezone(UTC)


def _resolve_weekday(local_now: datetime, text: str, match: re.Match[str]) -> datetime:
    weekday = _WEEKDAYS[match.group(1).lower()]
    force_next = "next " in text
    target_day = _next_weekday(local_now, weekday, force_next=force_next)
    if target_day.date() == local_now.date() and not force_next:
        hour = int(match.group(2))
        minute = int(match.group(3) or 0)
        candidate = _apply_clock(target_day, hour, minute, match.group(4))
        if candidate <= local_now:
            target_day = target_day + timedelta(days=7)
    resolved = _apply_clock(
        target_day,
        int(match.group(2)),
        int(match.group(3) or 0),
        match.group(4),
    )
    return resolved.astimezone(UTC)


def format_local(moment: datetime, timezone_name: str, fmt: str = "%a %d %b %H:%M") -> str:
    """Format a datetime in the user's timezone.

    Args:
        moment: Aware or naive UTC datetime.
        timezone_name: IANA timezone.
        fmt: strftime pattern.

    Returns:
        Formatted local time.
    """
    return to_local(moment, timezone_name).strftime(fmt)
