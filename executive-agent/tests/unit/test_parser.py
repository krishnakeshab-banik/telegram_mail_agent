"""Gmail parsing, HTML sanitizing, and bulk detection."""

import json
from pathlib import Path

from app.google.gmail_parser import html_to_text, parse_gmail_message

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_plain_text_is_preferred_and_scripts_are_not_required() -> None:
    payload = json.loads((FIXTURES / "msg-meeting.json").read_text(encoding="utf-8"))
    parsed = parse_gmail_message(payload)
    assert "next Tuesday at 3pm" in parsed.body_text
    assert parsed.meeting_links == ["https://meet.google.com/abc-defg-hij"]
    assert parsed.sender_email == "priya.shah@example.com"
    assert parsed.is_bulk is False


def test_newsletter_headers_are_bulk_and_html_scripts_are_removed() -> None:
    payload = json.loads((FIXTURES / "msg-newsletter.json").read_text(encoding="utf-8"))
    parsed = parse_gmail_message(payload)
    assert parsed.is_bulk is True
    assert parsed.bulk_reason == "list-unsubscribe"
    assert "steal" not in html_to_text("<script>steal()</script><p>Visible</p>")


def test_attachment_metadata_is_captured_without_downloading_bytes() -> None:
    payload = json.loads((FIXTURES / "msg-invoice.json").read_text(encoding="utf-8"))
    parsed = parse_gmail_message(payload)
    assert parsed.has_attachments is True
    assert parsed.attachments[0].filename == "invoice.txt"
    assert parsed.attachments[0].gmail_attachment_id == "att-invoice"
