"""The Telegram menu lists twelve commands. Aliases stay registered and hidden."""

from app.bot.app import _handler_for
from app.bot.catalog import COMMAND_MENU, COMMANDS, DESCRIPTION, SHORT_DESCRIPTION
from app.bot.formatters import help_text

_MENU = (
    "start",
    "today",
    "brief",
    "meet",
    "deadlines",
    "tasks",
    "folders",
    "waiting",
    "mail",
    "search",
    "settings",
    "help",
)


def test_menu_is_exactly_twelve_commands() -> None:
    names = [name for name, _blurb in COMMAND_MENU]
    assert names == list(_MENU)
    assert [spec.name for spec in COMMANDS if spec.in_menu] == list(_MENU)
    assert len(SHORT_DESCRIPTION) <= 120
    assert len(DESCRIPTION) <= 512
    assert all(3 <= len(blurb) <= 256 for _name, blurb in COMMAND_MENU)
    rendered = help_text()
    for name in _MENU:
        assert f"/{name}" in rendered
    assert rendered.split("Aliases:")[0].count("/mail") == 1
    assert "compose is /mail" in rendered
    assert len(rendered) <= 3900


def test_every_alias_resolves_and_merged_commands_share_a_handler() -> None:
    names = [spec.name for spec in COMMANDS]
    assert len(names) == len(set(names))
    for spec in COMMANDS:
        _handler_for(spec.handler)
        if spec.alias_of:
            target = next(item for item in COMMANDS if item.name == spec.alias_of)
            assert spec.handler == target.handler
            assert spec.in_menu is False
    hidden = {spec.name for spec in COMMANDS if not spec.in_menu}
    assert {"disconnect", "deleteme", "privacy", "admin", "compose", "important"} <= hidden
