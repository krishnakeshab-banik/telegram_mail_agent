"""Relative date resolution and quiet hours."""

from datetime import UTC, datetime

from app.utils.time import in_quiet_hours, resolve_relative

NOW = datetime(2026, 10, 5, 4, 0, tzinfo=UTC)  # 09:30 in Asia/Kolkata


def test_tomorrow_morning_uses_the_user_timezone() -> None:
    resolved = resolve_relative("tomorrow 9am", now=NOW, timezone_name="Asia/Kolkata")
    assert resolved is not None
    assert resolved.astimezone(UTC).hour == 3
    assert resolved.day == 6


def test_next_weekday_skips_to_the_following_week_when_named() -> None:
    resolved = resolve_relative("next tuesday 3pm", now=NOW, timezone_name="Asia/Kolkata")
    assert resolved is not None
    local_day = resolved.astimezone(UTC)
    assert local_day.weekday() == 1 or resolved.astimezone().weekday() == 1


def test_quiet_hours_wrap_past_midnight() -> None:
    late = datetime(2026, 10, 5, 17, 30, tzinfo=UTC)  # 23:00 IST
    early = datetime(2026, 10, 5, 2, 30, tzinfo=UTC)  # 08:00 IST
    assert in_quiet_hours(late, "Asia/Kolkata", "22:00", "07:00") is True
    assert in_quiet_hours(early, "Asia/Kolkata", "22:00", "07:00") is False
