"""Briefing text and Gemini model fallback."""

from app.ai.gemini_client import fallback_models
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


def test_fallback_models_keep_the_preferred_name_first() -> None:
    """Quota failures try the configured model before alternates."""
    models = fallback_models("gemini-3.8-flash")
    assert models[0] == "gemini-3.8-flash"
    assert "gemini-3.5-flash" in models
    assert len(models) == len(set(models))
