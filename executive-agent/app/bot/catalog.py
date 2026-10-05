"""One command registry. The Telegram menu is the commands marked in_menu."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandSpec:
    """A slash command, the handler key that runs it, and whether Telegram lists it."""

    name: str
    handler: str
    in_menu: bool
    alias_of: str = ""
    blurb: str = ""


def _menu(name: str, handler: str, blurb: str) -> CommandSpec:
    return CommandSpec(name, handler, True, "", blurb)


def _alias(name: str, handler: str, alias_of: str) -> CommandSpec:
    return CommandSpec(name, handler, False, alias_of, "")


def _hidden(name: str, handler: str) -> CommandSpec:
    return CommandSpec(name, handler, False, "", "")


def _folder(slug: str) -> CommandSpec:
    return CommandSpec(slug, f"folder:{slug}", False, "", "")


COMMANDS: tuple[CommandSpec, ...] = (
    _menu("start", "start", "Open Jarvis and connect Google"),
    _menu("today", "today", "Today's meetings, deadlines due within 24 hours, and pending replies"),
    _menu("brief", "brief", "Morning briefing of what matters"),
    _menu("meet", "meet", "Today's meetings and join links"),
    _menu("deadlines", "deadlines", "Upcoming dates and missed or overdue ones"),
    _menu("tasks", "tasks", "Open tasks you can mark done"),
    _menu("folders", "folders", "Smart folders for jobs, bills, codes, and the rest"),
    _menu("waiting", "waiting", "Replies you owe and replies you are waiting on"),
    _menu("mail", "mail", "Draft a new email. Nothing is sent until you confirm"),
    _menu("search", "search", "Find mail in plain language"),
    _menu("settings", "settings", "Reminders, quiet hours, timezone, notifications, and account"),
    _menu("help", "help", "What each command does"),
    _alias("compose", "mail", "mail"),
    _alias("followups", "waiting", "waiting"),
    _alias("categories", "folders", "folders"),
    _alias("preferences", "settings", "settings"),
    _alias("menu", "folders", "folders"),
    _alias("free", "meet", "meet"),
    _hidden("important", "important"),
    _hidden("unread", "unread"),
    _hidden("wrapup", "wrapup"),
    _hidden("calendar", "calendar"),
    _hidden("signup", "signup"),
    _hidden("privacy", "privacy"),
    _hidden("disconnect", "disconnect"),
    _hidden("deleteme", "deleteme"),
    _hidden("status", "status"),
    _hidden("errors", "errors"),
    _hidden("history", "history"),
    _hidden("pause", "pause"),
    _hidden("resume", "resume"),
    _hidden("focus", "focus"),
    _hidden("templates", "templates"),
    _hidden("suggest", "suggest"),
    _hidden("interests", "interests"),
    _hidden("done", "done"),
    _hidden("snooze", "snooze"),
    _hidden("meets", "folder:meets"),
    _hidden("admin", "admin"),
    _folder("jobs"),
    _folder("hackathons"),
    _folder("events"),
    _folder("scholarships"),
    _folder("opportunities"),
    _folder("bills"),
    _folder("orders"),
    _folder("travel"),
    _folder("finance"),
    _folder("academics"),
    _folder("otps"),
    _folder("spam"),
    _folder("newsletters"),
    _folder("filtered"),
    _folder("vip"),
    _folder("saved"),
    _folder("archive"),
)

COMMAND_MENU: tuple[tuple[str, str], ...] = tuple(
    (spec.name, spec.blurb) for spec in COMMANDS if spec.in_menu
)

SHORT_DESCRIPTION = (
    "Gmail assistant: folders, deadlines, and reply drafts. Nothing sends until you tap confirm."
)

DESCRIPTION = (
    "Personal executive assistant. I watch Gmail, keep deadlines and meetings, "
    "and draft replies. Nothing is sent until you confirm.\n\n"
    "/start /today /brief /meet /deadlines /tasks /folders /waiting /mail /search /settings /help"
)
