"""Briefing text stays compact when a section is empty."""

from app.bot.formatters import digest
from app.services.briefing_service import Digest


def test_empty_sections_do_not_say_none() -> None:
    """An empty briefing says nothing is queued instead of the word None."""
    text = digest(
        Digest(
            title="Morning briefing",
            important=[],
            meetings=[],
            deadlines=[],
            tasks=[],
            followups=[],
            focus="",
        )
    )
    assert "Nothing needs attention." in text
    assert "\nNone" not in text
