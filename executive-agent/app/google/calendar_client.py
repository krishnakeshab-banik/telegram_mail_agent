"""Thin Google Calendar wrapper, with a file-backed demo implementation."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from app.exceptions import CalendarApiError
from app.google.auth import GoogleAuth
from app.google.http import GoogleHttp

_BASE = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


@dataclass(frozen=True)
class RemoteEvent:
    """Event fields needed for conflict checks and listings."""

    event_id: str
    title: str
    start: datetime
    end: datetime
    location: str
    link: str


@dataclass(frozen=True)
class EventDraft:
    """Event the user has approved for creation or update."""

    title: str
    description: str
    start: datetime
    end: datetime
    timezone_name: str
    location: str
    link: str
    attendees: list[str]


class CalendarGateway(Protocol):
    """Calendar operations used by the calendar service."""

    async def list_events(self, start: datetime, end: datetime) -> list[RemoteEvent]:
        """Return events overlapping a window."""

    async def create_event(self, draft: EventDraft) -> str:
        """Create an event and return its Google id."""

    async def update_event(self, event_id: str, draft: EventDraft) -> str:
        """Update an event and return its id."""

    async def delete_event(self, event_id: str) -> None:
        """Delete an event."""

    async def aclose(self) -> None:
        """Release resources."""


class CalendarClient:
    """Live Calendar REST client."""

    def __init__(self, auth: GoogleAuth, *, requests_per_minute: int) -> None:
        """Store auth and the HTTP helper.

        Args:
            auth: Token provider.
            requests_per_minute: Local rate limit.
        """
        self._auth = auth
        self._http = GoogleHttp(
            requests_per_minute=requests_per_minute, error_type=CalendarApiError
        )

    async def list_events(self, start: datetime, end: datetime) -> list[RemoteEvent]:
        """List primary-calendar events in a window."""
        token = await self._auth.get_access_token()
        payload = await self._http.request(
            "GET",
            _BASE,
            token=token,
            params={
                "timeMin": start.isoformat(),
                "timeMax": end.isoformat(),
                "singleEvents": "true",
                "orderBy": "startTime",
            },
        )
        items = payload.get("items", [])
        if not isinstance(items, list):
            return []
        return [event for item in items if isinstance(item, dict) and (event := _remote(item))]

    async def create_event(self, draft: EventDraft) -> str:
        """Insert an event."""
        token = await self._auth.get_access_token()
        payload = await self._http.request("POST", _BASE, token=token, json_body=_body(draft))
        return str(payload.get("id", ""))

    async def update_event(self, event_id: str, draft: EventDraft) -> str:
        """Patch an event."""
        token = await self._auth.get_access_token()
        payload = await self._http.request(
            "PATCH",
            f"{_BASE}/{event_id}",
            token=token,
            json_body=_body(draft),
        )
        return str(payload.get("id", event_id))

    async def delete_event(self, event_id: str) -> None:
        """Delete an event."""
        token = await self._auth.get_access_token()
        await self._http.request("DELETE", f"{_BASE}/{event_id}", token=token)

    async def aclose(self) -> None:
        """Close the HTTP client."""
        await self._http.aclose()


class DemoCalendarClient:
    """File-backed calendar used when the app runs in demo mode."""

    def __init__(self, path: Path) -> None:
        """Store the JSON file used as the demo calendar.

        Args:
            path: Path to the demo calendar store.
        """
        self._path = path

    async def list_events(self, start: datetime, end: datetime) -> list[RemoteEvent]:
        """Return stored demo events that overlap the window."""
        events = []
        for item in self._load():
            remote = _remote(item)
            if remote and remote.start < end and remote.end > start:
                events.append(remote)
        return events

    async def create_event(self, draft: EventDraft) -> str:
        """Append a demo event."""
        rows = self._load()
        event_id = f"demo-event-{len(rows) + 1}"
        rows.append({"id": event_id, **_body(draft)})
        self._save(rows)
        return event_id

    async def update_event(self, event_id: str, draft: EventDraft) -> str:
        """Replace a stored demo event."""
        rows = [item for item in self._load() if item.get("id") != event_id]
        rows.append({"id": event_id, **_body(draft)})
        self._save(rows)
        return event_id

    async def delete_event(self, event_id: str) -> None:
        """Remove a stored demo event."""
        self._save([item for item in self._load() if item.get("id") != event_id])

    async def aclose(self) -> None:
        """Demo clients hold no network resources."""

    def _load(self) -> list[dict[str, object]]:
        if not self._path.is_file():
            return []
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    def _save(self, rows: list[dict[str, object]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(rows), encoding="utf-8")


def _body(draft: EventDraft) -> dict[str, object]:
    description = draft.description
    if draft.link and draft.link not in description:
        description = f"{description}\n{draft.link}".strip()
    return {
        "summary": draft.title,
        "description": description,
        "location": draft.location,
        "start": {"dateTime": draft.start.isoformat(), "timeZone": draft.timezone_name},
        "end": {"dateTime": draft.end.isoformat(), "timeZone": draft.timezone_name},
        "attendees": [{"email": email} for email in draft.attendees if email],
        "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 30}]},
    }


def _remote(item: dict[str, object]) -> RemoteEvent | None:
    start_raw = item.get("start")
    end_raw = item.get("end")
    start = _moment(start_raw)
    end = _moment(end_raw)
    if start is None or end is None:
        return None
    link = str(item.get("hangoutLink", "") or item.get("location", ""))
    return RemoteEvent(
        event_id=str(item.get("id", "")),
        title=str(item.get("summary", "")),
        start=start,
        end=end,
        location=str(item.get("location", "")),
        link=link,
    )


def _moment(value: object) -> datetime | None:
    if not isinstance(value, dict):
        return None
    text = str(value.get("dateTime") or value.get("date") or "")
    if not text:
        return None
    if len(text) == 10:
        text = f"{text}T00:00:00+00:00"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed
