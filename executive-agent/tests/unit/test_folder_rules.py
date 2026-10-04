"""Deadline anchoring, folder rules, OTP masking, and reply safety."""

from datetime import UTC, datetime

from app.services.extraction import _usable_task, resolve_when
from app.services.folder_rules import (
    classify_message,
    looks_like_otp,
    mask_code,
    phishing_reasons,
)
from app.services.folder_service import parse_folder_request
from app.services.reply_suggestion_service import ReplySuggestionService
from app.utils.time import describe_due


def test_deadline_today_is_anchored_to_the_email_and_becomes_overdue() -> None:
    """A two-day-old 'today' is overdue, never described as hours left."""
    received = datetime(2026, 10, 3, 4, 0, tzinfo=UTC)
    now = datetime(2026, 10, 5, 4, 0, tzinfo=UTC)
    due = resolve_when("today", "Asia/Kolkata", received)
    assert due is not None
    assert due < now
    label = describe_due(due, now)
    assert label == "overdue"
    assert "hours left" not in label


def test_junk_tasks_are_rejected() -> None:
    """Newsletter buttons are not stored as tasks."""
    assert _usable_task("unsubscribe") is False
    assert _usable_task("Please send the signed invoice") is True


def test_hackathon_is_also_a_deadline_and_otp_is_separate() -> None:
    """One message can land in more than one folder, and codes stay masked."""
    hits = classify_message(
        subject="Campus hackathon, deadline today",
        body="Prize pool and registration deadline today",
        sender="events@college.edu",
        category="other",
        is_bulk=False,
        requires_reply=False,
        has_meeting=False,
        has_deadline=True,
        is_vip=False,
    )
    slugs = [hit.slug for hit in hits]
    assert slugs[0] != "otps"
    assert "hackathons" in slugs
    assert "deadlines" in slugs
    assert looks_like_otp("Your OTP is 4403", "")
    assert mask_code("4403") == "•••• 03"


def test_phishing_is_reasons_not_a_trusting_summary() -> None:
    """Suspicious mail is labeled with reasons."""
    reasons = phishing_reasons("Verify your password now", "Use this bit.ly link")
    assert reasons
    assert all("thank" not in reason.lower() for reason in reasons)


def test_reply_variants_do_not_send_and_warn_on_missing_attachment() -> None:
    """Choosing a variant only builds a preview."""
    service = ReplySuggestionService()
    variants = service.variants(sender_name="Priya", subject="Invoice", instruction="")
    assert [item.label for item in variants] == ["Short", "Detailed", "Decline"]
    instructed = service.variants(
        sender_name="Priya",
        subject="Invoice",
        instruction="reply yes and ask for the invoice",
    )
    assert "yes" in instructed[0].body.lower()
    assert "invoice" in instructed[0].body.lower()
    preview = service.preview(
        to="priya@example.com",
        subject="Re: Invoice",
        body="The file is attached.",
        has_attachment=False,
    )
    assert "no attachment" in preview.warning
    assert preview.to == "priya@example.com"
    chips = service.chips()
    assert chips
    assert all(item.body for item in chips)


def test_plain_language_folder_keeps_useful_keywords() -> None:
    """Stop-words drop out of a create-folder sentence."""
    parsed = parse_folder_request("create folder Research for emails from my professor and arXiv")
    assert parsed is not None
    name, keywords = parsed
    assert name == "Research"
    assert "professor" in [word.lower() for word in keywords]
    assert "arxiv" in [word.lower() for word in keywords]
