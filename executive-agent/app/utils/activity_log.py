"""In-process activity log backed by a redacted JSONL file."""

import json
import threading
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SKIPPED_FIELDS = {"event", "level", "timestamp", "logger"}
_MAX_RECORDS = 500
_MAX_DETAIL = 500


@dataclass(frozen=True)
class ActivityRecord:
    """One redacted backend event."""

    timestamp: str
    level: str
    event: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        """Return a JSON-ready mapping."""
        return {
            "timestamp": self.timestamp,
            "level": self.level,
            "event": self.event,
            "detail": self.detail,
        }


class ActivityLog:
    """Keep the newest backend events in memory and append them to disk."""

    def __init__(self, path: Path | None, *, limit: int = _MAX_RECORDS) -> None:
        """Create an empty log.

        Args:
            path: JSONL file. None keeps events in memory only.
            limit: Maximum events retained in memory.
        """
        self._path = path
        self._records: deque[ActivityRecord] = deque(maxlen=limit)
        self._lock = threading.Lock()

    def add(self, event: dict[str, Any]) -> None:
        """Store one structured event.

        Args:
            event: Redacted structlog event dictionary.
        """
        record = _to_record(event)
        with self._lock:
            self._records.append(record)
            self._append(record)

    def load_existing(self) -> None:
        """Load the tail of the JSONL file into memory."""
        if self._path is None or not self._path.exists():
            return
        for line in _tail_lines(self._path, self._records.maxlen or _MAX_RECORDS):
            record = _from_line(line)
            if record is not None:
                self._records.append(record)

    def query(self, *, level: str = "", text: str = "", limit: int = 200) -> list[ActivityRecord]:
        """Return matching events, newest last.

        Args:
            level: Exact level name, or an empty string for every level.
            text: Case-insensitive match against the event name and detail.
            limit: Maximum rows to return.

        Returns:
            Matching records in chronological order.
        """
        needle = text.casefold()
        wanted = level.casefold()
        with self._lock:
            rows = list(self._records)
        matched = [row for row in rows if _matches(row, wanted, needle)]
        return matched[-max(1, min(limit, _MAX_RECORDS)) :]

    def _append(self, record: ActivityRecord) -> None:
        if self._path is None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record.as_dict(), ensure_ascii=True) + "\n")
        except OSError:
            return


_ACTIVE: ActivityLog | None = None


def configure_activity_log(path: Path | None) -> ActivityLog:
    """Install the process activity log and load any saved tail.

    Args:
        path: JSONL path, or None for memory only.

    Returns:
        The active log.
    """
    global _ACTIVE
    log = ActivityLog(path)
    log.load_existing()
    _ACTIVE = log
    return log


def get_activity_log() -> ActivityLog:
    """Return the process activity log, creating a memory log if needed."""
    global _ACTIVE
    if _ACTIVE is None:
        _ACTIVE = ActivityLog(None)
    return _ACTIVE


def _to_record(event: dict[str, Any]) -> ActivityRecord:
    parts = [
        f"{key}={_clip(value)}"
        for key, value in event.items()
        if key not in _SKIPPED_FIELDS and not str(key).startswith("_")
    ]
    return ActivityRecord(
        timestamp=str(event.get("timestamp", "")),
        level=str(event.get("level", "info")).lower(),
        event=str(event.get("event", "log")),
        detail=" ".join(parts)[:_MAX_DETAIL],
    )


def _from_line(line: str) -> ActivityRecord | None:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return ActivityRecord(
        timestamp=str(payload.get("timestamp", "")),
        level=str(payload.get("level", "info")),
        event=str(payload.get("event", "log")),
        detail=str(payload.get("detail", ""))[:_MAX_DETAIL],
    )


def _matches(row: ActivityRecord, level: str, needle: str) -> bool:
    if level and row.level != level:
        return False
    if not needle:
        return True
    return needle in f"{row.event} {row.detail}".casefold()


def _clip(value: object) -> str:
    if isinstance(value, str):
        return value.replace("\n", " ")[:180]
    return str(value)[:180]


def _tail_lines(path: Path, count: int) -> list[str]:
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            handle.seek(max(0, handle.tell() - 262_144))
            raw = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    return raw.splitlines()[-count:]
