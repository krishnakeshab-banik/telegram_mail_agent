"""Activity log filtering and persistence."""

from pathlib import Path

from app.utils.activity_log import ActivityLog


def test_query_filters_level_and_text(tmp_path: Path) -> None:
    """Only matching events are returned."""
    log = ActivityLog(tmp_path / "activity.jsonl")
    log.add(
        {"timestamp": "t1", "level": "error", "event": "gemini_request_failed", "detail": "404"}
    )
    log.add({"timestamp": "t2", "level": "info", "event": "agent_starting", "detail": "live"})
    found = log.query(level="error", text="gemini")
    assert len(found) == 1
    assert found[0].event == "gemini_request_failed"


def test_reload_reads_saved_tail(tmp_path: Path) -> None:
    """A new log instance sees events written by the previous one."""
    path = tmp_path / "activity.jsonl"
    ActivityLog(path).add(
        {"timestamp": "t", "level": "warning", "event": "retrying_call", "code": 429}
    )
    reloaded = ActivityLog(path)
    reloaded.load_existing()
    rows = reloaded.query(level="warning")
    assert rows[0].event == "retrying_call"
    assert "429" in rows[0].detail
