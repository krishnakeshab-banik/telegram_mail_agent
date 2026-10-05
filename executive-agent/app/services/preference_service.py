"""Inspectable user preferences, pause switch, and writing-style memory."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.gemini_client import GeminiClient
from app.ai.prompt_loader import load_prompt
from app.ai.schemas import StyleNoteSchema
from app.config import Settings
from app.constants import DEFAULT_CATEGORY_NOTIFY, Category
from app.db.base import session_scope
from app.db.models.preference import Preference
from app.db.models.style_note import StyleNote
from app.db.repositories.preference_repository import PreferenceRepository
from app.db.repositories.state_repository import AgentStateRepository, StyleNoteRepository
from app.utils.security import wrap_untrusted
from app.utils.time import parse_clock, utcnow

_TONES = {"formal", "friendly", "direct"}


@dataclass(frozen=True)
class UserPreferences:
    """Effective preferences after defaults are merged with stored overrides."""

    timezone: str
    briefing_hour: int
    briefing_minute: int
    wrapup_hour: int
    wrapup_minute: int
    quiet_start: str
    quiet_end: str
    signature: str
    tone: str
    importance_threshold: int
    apply_labels: bool
    category_notify: dict[str, bool]
    writing_style: str
    reminder_leads: tuple[int, ...]
    followup_nudge_hours: int
    reminders_override_quiet: bool


class PreferenceService:
    """Read and update preferences. Stored rows are the source the user can inspect."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        gemini: GeminiClient,
    ) -> None:
        """Store collaborators.

        Args:
            session_factory: Database session factory.
            settings: Default values used before the user overrides them.
            gemini: Client used to summarize draft edits. Optional in demo mode.
        """
        self._sessions = session_factory
        self._settings = settings
        self._gemini = gemini

    async def get(self) -> UserPreferences:
        """Return effective preferences."""
        stored = await self._stored()
        briefing = _clock(
            str(stored.get("briefing_time", "")),
            self._settings.briefing_hour,
            self._settings.briefing_minute,
        )
        wrapup = _clock(
            str(stored.get("wrapup_time", "")),
            self._settings.wrapup_hour,
            self._settings.wrapup_minute,
        )
        notify = dict(DEFAULT_CATEGORY_NOTIFY)
        raw_notify = stored.get("category_notify")
        if isinstance(raw_notify, dict):
            notify.update({str(key): bool(value) for key, value in raw_notify.items()})
        raw_leads = stored.get("reminder_leads", list(self._settings.reminder_leads))
        lead_values = (
            raw_leads if isinstance(raw_leads, list) else list(self._settings.reminder_leads)
        )
        raw_threshold = stored.get(
            "importance_threshold", self._settings.importance_notify_threshold
        )
        threshold = (
            raw_threshold
            if isinstance(raw_threshold, int)
            else self._settings.importance_notify_threshold
        )
        return UserPreferences(
            timezone=str(stored.get("timezone", self._settings.timezone)),
            briefing_hour=briefing[0],
            briefing_minute=briefing[1],
            wrapup_hour=wrapup[0],
            wrapup_minute=wrapup[1],
            quiet_start=str(stored.get("quiet_start", self._settings.quiet_hours_start)),
            quiet_end=str(stored.get("quiet_end", self._settings.quiet_hours_end)),
            signature=str(stored.get("signature", "")),
            tone=str(stored.get("tone", "direct")),
            importance_threshold=threshold,
            apply_labels=bool(stored.get("apply_labels", self._settings.apply_gmail_labels)),
            category_notify=notify,
            writing_style=str(stored.get("writing_style", "")),
            reminder_leads=tuple(int(item) for item in lead_values),
            followup_nudge_hours=_as_int(
                stored.get("followup_nudge_hours"),
                self._settings.followup_nudge_hours,
            ),
            reminders_override_quiet=_as_bool(stored.get("reminders_override_quiet"), default=True),
        )

    async def apply_command(self, text: str) -> str | None:
        """Apply a preference command, or return None when the text is not one.

        Args:
            text: Owner message.

        Returns:
            Confirmation text, or None when the message is not a preference edit.
        """
        parsed = _parse_preference(text.strip())
        if parsed is None:
            return None
        key, value = parsed
        if key == "quiet_window" and isinstance(value, dict):
            await self._set("quiet_start", value["quiet_start"])
            await self._set("quiet_end", value["quiet_end"])
            return "Updated quiet hours."
        await self._set(key, value)
        return f"Updated {key.replace('_', ' ')}."

    async def set_reminders_override(self, enabled: bool) -> None:
        """Store whether reminders may arrive during quiet hours. Default is on."""
        await self._set("reminders_override_quiet", enabled)
        from app.db.repositories.user_repository import UserRepository
        from app.db.user_context import peek_user_id

        user_id = peek_user_id()
        if user_id is None:
            return
        async with session_scope(self._sessions) as session:
            user = await UserRepository(session).get(user_id)
            if user is not None:
                user.reminders_override_quiet = enabled

    async def set_reminder_leads(self, leads: tuple[int, ...]) -> None:
        """Store the reminder offsets, in minutes, for this user."""
        await self._set("reminder_leads", [int(item) for item in leads])

    async def set_tone(self, tone: str) -> None:
        """Set the default draft tone."""
        if tone in _TONES:
            await self._set("tone", tone)

    async def toggle_labels(self) -> bool:
        """Toggle Gmail label application and return the new value."""
        current = (await self.get()).apply_labels
        await self._set("apply_labels", not current)
        return not current

    async def cycle_threshold(self) -> int:
        """Cycle the notify threshold through 40, 60, and 80."""
        current = (await self.get()).importance_threshold
        nxt = {40: 60, 60: 80, 80: 40}.get(current, 60)
        await self._set("importance_threshold", nxt)
        return nxt

    async def set_category_notify(self, category: str, enabled: bool) -> None:
        """Turn instant alerts on or off for one category."""
        prefs = await self.get()
        updated = dict(prefs.category_notify)
        if category in {item.value for item in Category}:
            updated[category] = enabled
            await self._set("category_notify", updated)

    async def learn_style(self, original: str, edited: str) -> None:
        """Store a writing-style note when a sent reply differs from the draft."""
        if original.strip() == edited.strip():
            return
        note = await self._style_note(original, edited)
        if not note:
            return
        async with session_scope(self._sessions) as session:
            await StyleNoteRepository(session).add(StyleNote(note=note[:500]))
        current = (await self.get()).writing_style
        combined = (current + "\n" + note).strip()
        await self._set("writing_style", combined[-2000:])

    async def extra(self, key: str, default: str = "") -> str:
        """Return one stored string preference."""
        value = (await self._stored()).get(key, default)
        return value if isinstance(value, str) else default

    async def set_extra(self, key: str, value: str) -> None:
        """Store one string preference."""
        await self._set(key, value)

    async def focus_active(self) -> bool:
        """Return whether focus mode is still silencing ordinary alerts."""
        raw = await self.extra("focus_until")
        if not raw:
            return False
        try:
            moment = datetime.fromisoformat(raw)
        except ValueError:
            return False
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        return moment > utcnow()

    async def style_notes(self) -> str:
        """Return the learned writing-style text."""
        return (await self.get()).writing_style

    async def is_paused(self) -> bool:
        """Return whether the kill switch is on."""
        async with session_scope(self._sessions) as session:
            return (await AgentStateRepository(session).get_singleton()).paused

    async def set_paused(self, paused: bool) -> None:
        """Set the kill switch."""
        async with session_scope(self._sessions) as session:
            state = await AgentStateRepository(session).get_singleton()
            state.paused = paused
            state.updated_at = utcnow()

    async def remember_chat(self, chat_id: int) -> None:
        """Remember where scheduled messages should be delivered."""
        async with session_scope(self._sessions) as session:
            state = await AgentStateRepository(session).get_singleton()
            state.telegram_chat_id = chat_id

    async def chat_id(self) -> int | None:
        """Return the Telegram chat that should receive alerts."""
        async with session_scope(self._sessions) as session:
            return (await AgentStateRepository(session).get_singleton()).telegram_chat_id

    async def mark_digest(self, field: str, day: str) -> bool:
        """Record a daily digest as sent. Return False if it was already sent.

        Args:
            field: Either briefing or wrapup.
            day: Local date in ISO format.
        """
        async with session_scope(self._sessions) as session:
            state = await AgentStateRepository(session).get_singleton()
            current = state.last_briefing_on if field == "briefing" else state.last_wrapup_on
            if current == day:
                return False
            if field == "briefing":
                state.last_briefing_on = day
            else:
                state.last_wrapup_on = day
            return True

    async def _style_note(self, original: str, edited: str) -> str:
        if not self._gemini.enabled:
            return "Prefers the edited wording over the generated draft."
        payload = await self._gemini.generate_json(
            system_prompt=load_prompt("style_extract"),
            user_prompt="\n".join(
                [
                    wrap_untrusted("original_draft", original[:2000]),
                    wrap_untrusted("edited_text", edited[:2000]),
                ]
            ),
            schema=StyleNoteSchema,
        )
        return StyleNoteSchema.model_validate(payload).note.strip()

    async def _stored(self) -> dict[str, object]:
        async with session_scope(self._sessions) as session:
            rows = await PreferenceRepository(session).list_all()
        parsed: dict[str, object] = {}
        for row in rows:
            parsed[row.key] = json.loads(row.value_json)
        return parsed

    async def _set(self, key: str, value: object) -> None:
        async with session_scope(self._sessions) as session:
            repo = PreferenceRepository(session)
            existing = await repo.get(key)
            encoded = json.dumps(value)
            if existing is None:
                await repo.add(Preference(key=key, value_json=encoded, updated_at=utcnow()))
                return
            existing.value_json = encoded
            existing.updated_at = utcnow()


def _as_int(value: object, default: int) -> int:
    return value if isinstance(value, int) else default


def _as_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "off", "no"}
    return default


def _clock(value: str, default_hour: int, default_minute: int) -> tuple[int, int]:
    parsed = parse_clock(value)
    if parsed is None:
        return default_hour, default_minute
    return parsed


def _parse_preference(text: str) -> tuple[str, object] | None:
    lowered = text.lower()
    if lowered.startswith("timezone "):
        return "timezone", text.split(None, 1)[1].strip()
    if lowered.startswith("tone "):
        tone = lowered.split(None, 1)[1].strip()
        return ("tone", tone) if tone in _TONES else None
    if lowered.startswith("quiet "):
        window = lowered.split(None, 1)[1]
        if "-" not in window:
            return None
        start, end = (part.strip() for part in window.split("-", 1))
        if parse_clock(start) and parse_clock(end):
            return "quiet_window", {"quiet_start": start, "quiet_end": end}
    if lowered.startswith("briefing "):
        clock = parse_clock(lowered.split(None, 1)[1])
        if clock:
            return "briefing_time", f"{clock[0]:02d}:{clock[1]:02d}"
    if lowered.startswith("wrapup "):
        clock = parse_clock(lowered.split(None, 1)[1])
        if clock:
            return "wrapup_time", f"{clock[0]:02d}:{clock[1]:02d}"
    if lowered.startswith("signature "):
        return "signature", text.split(None, 1)[1].strip()
    if lowered.startswith("threshold "):
        raw = lowered.split(None, 1)[1]
        if raw.isdigit() and 0 <= int(raw) <= 100:
            return "importance_threshold", int(raw)
    if lowered in {"labels on", "labels off"}:
        return "apply_labels", lowered.endswith("on")
    return None
