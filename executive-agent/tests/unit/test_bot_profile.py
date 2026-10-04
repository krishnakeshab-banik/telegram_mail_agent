"""The Telegram profile lists every registered command within Telegram's length limits."""

from app.bot.app import _COMMANDS
from app.bot.catalog import COMMAND_MENU, DESCRIPTION, SHORT_DESCRIPTION
from app.bot.formatters import help_text


def test_profile_covers_every_command_and_fits_telegram() -> None:
    """Description, short description, and the slash menu stay within Telegram limits."""
    names = [name for name, _blurb in COMMAND_MENU]
    assert set(names) == set(_COMMANDS)
    assert len(names) == len(set(names))
    assert len(SHORT_DESCRIPTION) <= 120
    assert len(DESCRIPTION) <= 512
    assert all(3 <= len(blurb) <= 256 for _name, blurb in COMMAND_MENU)
    rendered = help_text()
    assert "/folders" in rendered
    assert "/suggest" in rendered
    assert len(rendered) <= 3900
