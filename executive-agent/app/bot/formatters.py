"""Telegram message text. Dynamic values are HTML-escaped."""

import html

from app.bot.catalog import COMMAND_MENU, SHORT_DESCRIPTION
from app.constants import URGENCY_BADGES
from app.services.audit_service import HistoryEntry, StatusSnapshot
from app.services.briefing_service import Digest
from app.services.notifier import AlertPlan
from app.services.preference_service import UserPreferences
from app.services.reminder_service import DueReminder
from app.services.reply_service import DraftPreview

_LIMIT = 3900


def welcome() -> str:
    """Return the /start message."""
    return (
        "<b>Executive Agent</b>\n"
        f"{esc(SHORT_DESCRIPTION)}\n"
        "Send /signup to connect Gmail. Write a new mail with "
        "/mail person@example.com and what you want to say.\n"
        "Nothing is sent, and Gmail is not changed, until you confirm it.\n\n"
        "Try /folders, /brief, or ask “what’s pending this week?”"
    )


def help_text() -> str:
    """Return each menu command once, grouped, plus the aliases."""
    lines = ["<b>Commands</b>", esc(SHORT_DESCRIPTION), ""]
    grouped = {
        "Today": ("start", "today", "brief", "meet"),
        "Work": ("deadlines", "tasks", "waiting", "folders"),
        "Mail": ("mail", "search"),
        "Account": ("settings", "help"),
    }
    blurbs = dict(COMMAND_MENU)
    for title, names in grouped.items():
        lines.append(f"<b>{title}</b>")
        lines.extend(f"/{esc(name)} — {esc(blurbs[name])}" for name in names if name in blurbs)
        lines.append("")
    lines.append(
        "Aliases: /compose is /mail, /followups is /waiting, /categories is /folders, "
        "/preferences is /settings. /important and /unread open those sections of /brief. "
        "Folder views such as /jobs are also under /folders."
    )
    lines.extend(
        [
            "",
            "Folder search: <code>/jobs machine learning</code>",
            "Custom folder: <code>create folder Research for professor and arXiv</code>, then yes.",
            "Instruction reply: <code>reply yes and ask for the invoice</code>",
            "Save a template: <code>/templates save Thanks :: Thanks, {name}.</code>",
            "Preferences: <code>timezone Asia/Kolkata</code>, <code>tone formal</code>, "
            "<code>quiet 22:00-07:00</code>, <code>briefing 08:00</code>, "
            "<code>vip add name@example.com</code>, <code>mute name@example.com</code>.",
        ]
    )
    return _clip("\n".join(lines))


def email_alert(plan: AlertPlan) -> str:
    """Format an instant email alert."""
    badge = URGENCY_BADGES.get(plan.urgency, plan.urgency.upper())
    lines = [
        f"<b>{esc(badge)}</b> · {esc(plan.category)}",
        f"<b>{esc(plan.subject)}</b>",
        esc(plan.sender_name or plan.sender_email),
        esc(plan.summary),
    ]
    if plan.deadline_lines:
        lines.append("Deadlines: " + esc("; ".join(plan.deadline_lines)))
    if plan.task_lines:
        lines.append("Tasks: " + esc("; ".join(plan.task_lines)))
    if plan.meeting_line:
        lines.append("Meeting: " + esc(plan.meeting_line))
    return _clip("\n".join(lines))


def draft_preview(preview: DraftPreview, *, warning: str = "") -> str:
    """Format a reply that is waiting for Send."""
    lines = [
        f"<b>Draft to {esc(preview.recipient)}</b>",
        esc(preview.subject),
        "",
        esc(preview.body),
        "",
        "Nothing is sent until you tap Send.",
    ]
    if warning:
        lines.append(esc(warning))
    return _clip("\n".join(lines))


def event_confirmation(title: str, when: str, warning: str) -> str:
    """Format a calendar confirmation card."""
    lines = ["<b>Add to calendar?</b>", esc(title), esc(when)]
    if warning:
        lines.append(esc(warning))
    lines.append("This stays a proposal until you confirm.")
    return "\n".join(lines)


def today_text(
    meetings: list[tuple[str, str]], deadlines: list[str], pending: list[str]
) -> str:
    """Format today's meetings, with join links, plus deadlines and pending replies."""
    parts = ["<b>Today</b>", _linked("Meetings", meetings), _section("Deadlines", deadlines)]
    parts.append(_section("Pending replies", pending))
    return _clip("\n\n".join(parts))


def meetings_text(meetings: list[tuple[str, str]]) -> str:
    """Format today's meetings and their join links."""
    return _clip(_linked("Meetings", meetings))


def named_section(title: str, rows: list[str]) -> str:
    """Format one briefing section."""
    return _clip(_section(title, rows))


def digest(item: Digest) -> str:
    """Format a compact briefing. Empty sections are omitted."""
    sections = [f"<b>{esc(item.title)}</b>"]
    named = [
        ("Important", item.important),
        ("Meetings", item.meetings),
        ("Deadlines", item.deadlines),
        ("Tasks", item.tasks),
        ("Waiting on you", item.waiting_on_you),
        ("Waiting on others", item.waiting_on_others),
        ("Unread", item.unread),
    ]
    for title, rows in named:
        if rows:
            sections.append(_section(title, rows[:3]))
    if item.focus:
        sections.append("<b>Focus</b>\n" + esc(item.focus))
    if len(sections) == 1:
        sections.append("Nothing needs attention.")
    return _clip("\n\n".join(sections))


def folder_menu(rows: list[tuple[str, int]]) -> str:
    """Format folder names with active counts."""
    if not rows:
        return "<b>Folders</b>\nNo folders yet."
    body = " | ".join(f"{esc(title)} ({count})" for title, count in rows)
    return f"<b>Folders</b>\n{body}"


def folder_cards(title: str, cards: list[tuple[str, str, str]]) -> str:
    """Format one page of folder cards."""
    if not cards:
        return f"<b>{esc(title)}</b>\nNothing in this folder."
    lines = [f"<b>{esc(title)}</b>"]
    for heading, sender, detail in cards:
        lines.append(f"• {esc(heading)}\n  {esc(sender)} · {esc(detail)}")
    return _clip("\n".join(lines))


def reply_choices(variants: list[tuple[str, str]], warning: str = "") -> str:
    """Format suggested replies. They are not sent."""
    lines = ["<b>Reply suggestions</b>"]
    for index, (label, body) in enumerate(variants, start=1):
        lines.append(f"{index}. <b>{esc(label)}</b>\n{esc(body)}")
    lines.append("Nothing is sent until you tap Send.")
    if warning:
        lines.append(esc(warning))
    return _clip("\n\n".join(lines))


def error_list(rows: list[tuple[str, str]]) -> str:
    """Format recent backend errors."""
    if not rows:
        return "<b>Errors</b>\nNo recent errors."
    lines = ["<b>Errors</b>"]
    for source, message in rows:
        lines.append(f"• {esc(source)}: {esc(message)}")
    return _clip("\n".join(lines))


def bullet_list(title: str, rows: list[str]) -> str:
    """Format a titled list."""
    if not rows:
        return f"<b>{esc(title)}</b>\nNothing to show."
    body = "\n".join(f"• {esc(row)}" for row in rows[:15])
    return _clip(f"<b>{esc(title)}</b>\n{body}")


def preferences(prefs: UserPreferences, vips: list[str], muted: list[str]) -> str:
    """Format the preference card."""
    notify = ", ".join(name for name, enabled in prefs.category_notify.items() if enabled)
    lines = [
        "<b>Preferences</b>",
        f"Timezone: {esc(prefs.timezone)}",
        f"Briefing: {prefs.briefing_hour:02d}:{prefs.briefing_minute:02d}",
        f"Quiet hours: {esc(prefs.quiet_start)}–{esc(prefs.quiet_end)}",
        f"Tone: {esc(prefs.tone)}",
        f"Threshold: {prefs.importance_threshold}",
        f"Gmail labels: {'on' if prefs.apply_labels else 'off'}",
        f"Instant categories: {esc(notify)}",
        f"VIPs: {esc(', '.join(vips) or 'none')}",
        f"Muted: {esc(', '.join(muted) or 'none')}",
        f"Style: {esc(prefs.writing_style or 'none yet')}",
    ]
    return _clip("\n".join(lines))


def history(entries: list[HistoryEntry]) -> str:
    """Format audit history."""
    if not entries:
        return "<b>History</b>\nNo actions yet."
    rows = [
        f"{esc(entry.created_at)} · {esc(entry.action_type)} · {esc(entry.approval_status)}\n{esc(entry.summary)}"
        for entry in entries
    ]
    return _clip("<b>History</b>\n\n" + "\n\n".join(rows))


def status(snapshot: StatusSnapshot) -> str:
    """Format /status."""
    state = "paused" if snapshot.paused else "running"
    google = "linked" if snapshot.google_linked else "not linked"
    return (
        f"<b>Status</b> {state}\n"
        f"Mode: {esc(snapshot.mode)}\n"
        f"Google: {google}\n"
        f"Mailbox: {esc(snapshot.mailbox or 'not linked')}\n"
        f"Last sync: {esc(snapshot.last_sync_at)}\n"
        f"Mail in the last 24h: {snapshot.synced_today}\n"
        f"Queue: {snapshot.queue_size}\n"
        f"Pending approvals: {snapshot.pending_approvals}\n"
        f"Errors (24h): {snapshot.errors_24h}\n"
        f"Last sync error: {esc(snapshot.last_error or 'none')}\n"
        f"Last Gemini error: {esc(snapshot.last_gemini_error or 'none')}"
    )


def categories(counts: dict[str, int]) -> str:
    """Format category counts."""
    if not counts:
        return "<b>Categories</b>\nNo classified mail yet."
    rows = [f"{esc(name)}: {count}" for name, count in sorted(counts.items())]
    return "<b>Categories</b>\n" + "\n".join(rows)


def reminder(item: DueReminder) -> str:
    """Format a reminder."""
    lines = [f"<b>Reminder</b> {esc(item.title)}", esc(item.when_label)]
    if item.link:
        lines.append(esc(item.link))
    if item.context:
        lines.append(esc(item.context))
    return _clip("\n".join(lines))


def thread_summary(summary: object) -> str:
    """Format a thread summary model."""
    participants = getattr(summary, "participants", [])
    timeline = getattr(summary, "timeline", [])
    decisions = getattr(summary, "decisions", [])
    questions = getattr(summary, "open_questions", [])
    status = getattr(summary, "latest_status", "")
    parts = [
        "<b>Thread</b>",
        "People: " + esc(", ".join(participants)),
        _section("Timeline", list(timeline)),
        _section("Decisions", list(decisions)),
        _section("Open questions", list(questions)),
        esc(str(status)),
    ]
    return _clip("\n\n".join(parts))


def plain(text: str) -> str:
    """Escape a single block of service text."""
    return _clip(esc(text))


def esc(value: str) -> str:
    """Escape text for Telegram HTML."""
    return html.escape(value, quote=False)


def _linked(title: str, rows: list[tuple[str, str]]) -> str:
    if not rows:
        return f"<b>{esc(title)}</b>\nNothing yet."
    lines = []
    for label, url in rows[:6]:
        link = ""
        if url.startswith("http://") or url.startswith("https://"):
            link = f' <a href="{html.escape(url, quote=True)}">join</a>'
        lines.append(f"• {esc(label)}{link}")
    return f"<b>{esc(title)}</b>\n" + "\n".join(lines)


def _section(title: str, rows: list[str]) -> str:
    if not rows:
        return f"<b>{esc(title)}</b>\nNothing yet."
    body = "\n".join(f"• {esc(row)}" for row in rows[:6])
    return f"<b>{title}</b>\n{body}"


def _clip(value: str) -> str:
    if len(value) <= _LIMIT:
        return value
    return value[: _LIMIT - 1] + "…"
