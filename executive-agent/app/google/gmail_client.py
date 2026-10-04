"""Thin Gmail API wrapper. Demo mode reads local fixtures instead of the network."""

import json
from pathlib import Path
from typing import Any, Protocol

from app.exceptions import GmailApiError
from app.google.http import GoogleHttp

_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


class TokenSource(Protocol):
    """Anything that can produce a Google bearer token."""

    async def get_access_token(self) -> str:
        """Return a bearer token."""


class MailboxClient(Protocol):
    """Operations the sync and reply services need from Gmail."""

    async def get_profile(self) -> tuple[str, str]:
        """Return the mailbox address and the current history id."""

    async def list_history_ids(self, start_history_id: str) -> tuple[list[str], str]:
        """Return message ids added since a history cursor, plus the new cursor."""

    async def list_message_ids(self, query: str) -> list[str]:
        """Return message ids matching a Gmail search query."""

    async def get_message(self, message_id: str) -> dict[str, Any]:
        """Return one full message resource."""

    async def get_thread_messages(self, thread_id: str) -> list[dict[str, Any]]:
        """Return full message resources in a thread."""

    async def send_raw(self, raw: str, thread_id: str) -> str:
        """Send a base64url RFC822 message and return the new message id."""

    async def list_labels(self) -> dict[str, str]:
        """Return a map of label name to label id."""

    async def create_label(self, name: str) -> str:
        """Create a label and return its id."""

    async def modify_labels(self, message_id: str, add: list[str], remove: list[str]) -> None:
        """Add and remove label ids on one message."""

    async def get_attachment(self, message_id: str, attachment_id: str) -> bytes:
        """Download attachment bytes."""

    async def aclose(self) -> None:
        """Release network resources."""


class GmailClient:
    """Live Gmail REST client."""

    def __init__(self, auth: TokenSource, *, requests_per_minute: int) -> None:
        """Store auth and the shared HTTP helper.

        Args:
            auth: Token provider.
            requests_per_minute: Local rate limit.
        """
        self._auth = auth
        self._http = GoogleHttp(requests_per_minute=requests_per_minute, error_type=GmailApiError)

    async def get_profile(self) -> tuple[str, str]:
        """Return the mailbox address and history id."""
        payload = await self._get(f"{_BASE}/profile", {"fields": "emailAddress,historyId"})
        return str(payload.get("emailAddress", "")), str(payload.get("historyId", ""))

    async def list_history_ids(self, start_history_id: str) -> tuple[list[str], str]:
        """Return newly added message ids and the latest history id."""
        params: dict[str, Any] = {
            "startHistoryId": start_history_id,
            "historyTypes": "messageAdded",
        }
        identifiers: list[str] = []
        latest = start_history_id
        while True:
            payload = await self._get(f"{_BASE}/history", params)
            latest = str(payload.get("historyId", latest))
            identifiers.extend(_history_ids(payload))
            token = payload.get("nextPageToken")
            if not token:
                return identifiers, latest
            params["pageToken"] = token

    async def list_message_ids(self, query: str) -> list[str]:
        """Return up to 50 message ids for a search query."""
        payload = await self._get(
            f"{_BASE}/messages",
            {"q": query, "maxResults": 50, "fields": "messages/id"},
        )
        messages = payload.get("messages", [])
        if not isinstance(messages, list):
            return []
        return [str(item.get("id", "")) for item in messages if isinstance(item, dict)]

    async def get_message(self, message_id: str) -> dict[str, Any]:
        """Return a full message resource."""
        return await self._get(f"{_BASE}/messages/{message_id}", {"format": "full"})

    async def get_thread_messages(self, thread_id: str) -> list[dict[str, Any]]:
        """Return full messages for a thread."""
        payload = await self._get(f"{_BASE}/threads/{thread_id}", {"format": "full"})
        messages = payload.get("messages", [])
        if not isinstance(messages, list):
            return []
        return [item for item in messages if isinstance(item, dict)]

    async def send_raw(self, raw: str, thread_id: str) -> str:
        """Send mail in an existing thread."""
        body: dict[str, Any] = {"raw": raw}
        if thread_id:
            body["threadId"] = thread_id
        payload = await self._send(f"{_BASE}/messages/send", body)
        return str(payload.get("id", ""))

    async def list_labels(self) -> dict[str, str]:
        """Return label names mapped to ids."""
        payload = await self._get(f"{_BASE}/labels", None)
        labels = payload.get("labels", [])
        if not isinstance(labels, list):
            return {}
        return {
            str(item.get("name", "")): str(item.get("id", ""))
            for item in labels
            if isinstance(item, dict)
        }

    async def create_label(self, name: str) -> str:
        """Create a user label."""
        payload = await self._send(
            f"{_BASE}/labels",
            {"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"},
        )
        return str(payload.get("id", ""))

    async def modify_labels(self, message_id: str, add: list[str], remove: list[str]) -> None:
        """Add or remove labels on a message."""
        await self._send(
            f"{_BASE}/messages/{message_id}/modify",
            {"addLabelIds": add, "removeLabelIds": remove},
        )

    async def get_attachment(self, message_id: str, attachment_id: str) -> bytes:
        """Download and decode attachment bytes."""
        import base64

        payload = await self._get(
            f"{_BASE}/messages/{message_id}/attachments/{attachment_id}", None
        )
        data = str(payload.get("data", ""))
        padded = data + "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(padded.encode("utf-8"))

    async def aclose(self) -> None:
        """Close the HTTP client."""
        await self._http.aclose()

    async def _get(self, url: str, params: dict[str, Any] | None) -> dict[str, Any]:
        token = await self._auth.get_access_token()
        return await self._http.request("GET", url, token=token, params=params)

    async def _send(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        token = await self._auth.get_access_token()
        return await self._http.request("POST", url, token=token, json_body=body)


class DemoGmailClient:
    """Fixture-backed mailbox used by demo mode and tests."""

    def __init__(self, fixture_dir: Path, outbox_path: Path) -> None:
        """Load fixtures and remember where demo sends are recorded.

        Args:
            fixture_dir: Directory of Gmail message JSON files.
            outbox_path: File that records messages "sent" in demo mode.
        """
        self._fixture_dir = fixture_dir
        self._outbox_path = outbox_path
        self._messages = _load_fixtures(fixture_dir)

    async def get_profile(self) -> tuple[str, str]:
        """Return a stable demo mailbox identity."""
        return "owner@example.com", "1000"

    async def list_history_ids(self, start_history_id: str) -> tuple[list[str], str]:
        """Return every fixture id. The database dedupes already stored mail."""
        del start_history_id
        return list(self._messages), "1000"

    async def list_message_ids(self, query: str) -> list[str]:
        """Return fixture ids. The query is ignored because the set is small."""
        del query
        return list(self._messages)

    async def get_message(self, message_id: str) -> dict[str, Any]:
        """Return one fixture or a stored outbox message."""
        if message_id in self._messages:
            return self._messages[message_id]
        for item in _read_outbox(self._outbox_path):
            if item.get("id") == message_id:
                return item
        raise GmailApiError("Demo message was not found.", 404)

    async def get_thread_messages(self, thread_id: str) -> list[dict[str, Any]]:
        """Return fixtures that share a thread id."""
        return [item for item in self._messages.values() if item.get("threadId") == thread_id]

    async def send_raw(self, raw: str, thread_id: str) -> str:
        """Record a sent message locally and return a demo id."""
        message_id = f"demo-sent-{len(_read_outbox(self._outbox_path)) + 1}"
        entry = {"id": message_id, "threadId": thread_id, "raw": raw}
        _append_outbox(self._outbox_path, entry)
        return message_id

    async def list_labels(self) -> dict[str, str]:
        """Return no remote labels in demo mode."""
        return {}

    async def create_label(self, name: str) -> str:
        """Return a deterministic demo label id."""
        return f"Label_{name}"

    async def modify_labels(self, message_id: str, add: list[str], remove: list[str]) -> None:
        """Accept label changes without a network call."""
        del message_id, add, remove

    async def get_attachment(self, message_id: str, attachment_id: str) -> bytes:
        """Load attachment bytes saved next to fixtures."""
        path = self._fixture_dir / "files" / f"{message_id}-{attachment_id}"
        if not path.is_file():
            raise GmailApiError("Demo attachment was not found.", 404)
        return path.read_bytes()

    async def aclose(self) -> None:
        """Demo clients hold no network resources."""


def _history_ids(payload: dict[str, Any]) -> list[str]:
    identifiers: list[str] = []
    history = payload.get("history", [])
    if not isinstance(history, list):
        return identifiers
    for record in history:
        if not isinstance(record, dict):
            continue
        added = record.get("messagesAdded", [])
        if not isinstance(added, list):
            continue
        for item in added:
            if isinstance(item, dict) and isinstance(item.get("message"), dict):
                identifiers.append(str(item["message"].get("id", "")))
    return [item for item in identifiers if item]


def _load_fixtures(directory: Path) -> dict[str, dict[str, Any]]:
    messages: dict[str, dict[str, Any]] = {}
    if not directory.is_dir():
        return messages
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and payload.get("id"):
            messages[str(payload["id"])] = payload
    return messages


def _read_outbox(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                rows.append(parsed)
    return rows


def _append_outbox(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")
