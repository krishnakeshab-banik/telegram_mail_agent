"""Folder counts, opportunity status, and the OTP vault."""

from datetime import UTC, datetime, timedelta

from app.db.base import session_scope
from app.db.models.analysis import EmailAnalysis
from app.db.models.email import EmailMessage
from app.db.repositories.analysis_repository import AnalysisRepository
from app.db.repositories.email_repository import EmailRepository
from app.db.repositories.folder_repository import FolderRepository
from app.services.container import Container
from app.utils.time import utcnow


async def _store(agent: Container, *, gmail_id: str, subject: str, body: str) -> int:
    async with session_scope(agent.sessions) as session:
        message = await EmailRepository(session).add(
            EmailMessage(
                gmail_message_id=gmail_id,
                thread_id=gmail_id,
                sender_email="events@example.com",
                sender_name="Events",
                subject=subject,
                body_text=body,
                received_at=datetime(2026, 10, 3, 4, 0, tzinfo=UTC),
                processed_at=datetime(2026, 10, 3, 5, 0, tzinfo=UTC),
            )
        )
        await AnalysisRepository(session).add(
            EmailAnalysis(
                email_id=message.id,
                category="other",
                importance_score=70,
                summary="stored for a folder test",
                deadlines_json="[]",
                action_items_json="[]",
                meeting_json="{}",
            )
        )
        return message.id


async def test_folder_counts_match_and_job_status_advances(agent: Container) -> None:
    """Counts come from links, and a job can move to applied."""
    email_id = await _store(
        agent,
        gmail_id="job-1",
        subject="Internship opening for a machine learning engineer",
        body="We are hiring. Stipend included. Role: ML engineer.",
    )
    slugs = await agent.folders.assign_email(email_id)
    assert "jobs" in slugs
    counts = {item.slug: item.count for item in await agent.folders.counts()}
    assert counts["jobs"] == 1
    async with session_scope(agent.sessions) as session:
        item = await FolderRepository(session).opportunity_for_email(email_id, "jobs")
    assert item is not None
    assert item.score >= 30
    assert "machine learning" in item.reason.lower() or item.score > 0
    title = await agent.folders.set_status(item.id, "applied")
    assert title
    async with session_scope(agent.sessions) as session:
        updated = await FolderRepository(session).opportunity_for_email(email_id, "jobs")
    assert updated is not None
    assert updated.status == "applied"


async def test_otp_is_masked_and_not_an_alert(agent: Container) -> None:
    """OTP mail is stored masked and skipped by the notifier."""
    email_id = await _store(
        agent,
        gmail_id="otp-1",
        subject="Your OTP is 4403",
        body="Verification code 4403",
    )
    slugs = await agent.folders.assign_email(email_id)
    assert "otps" in slugs
    masked = await agent.otp.remember(email_id, "login@example.com", "Your OTP is 4403")
    code, seconds = await agent.otp.reveal(email_id)
    assert masked == "•••• 03"
    assert code == "4403"
    assert seconds == 60
    await agent.preferences.apply_command("quiet 00:00-00:00")
    await agent.pipeline.process(email_id)
    plans = await agent.notifier.claim_ready()
    assert all(plan.email_id != email_id for plan in plans)


async def test_custom_folder_matches_new_mail(agent: Container) -> None:
    """A confirmed plain-language folder files later mail."""
    slug = await agent.folders.create_custom("Research", ["arxiv", "professor"])
    email_id = await _store(
        agent,
        gmail_id="arxiv-1",
        subject="arXiv abstract from your professor",
        body="New paper on the reading list",
    )
    slugs = await agent.folders.assign_email(email_id)
    assert slug in slugs


async def test_focus_holds_ordinary_mail_and_a_staged_reply_is_not_sent(
    agent: Container,
) -> None:
    """Focus mode keeps a normal alert, and a chosen reply only opens a preview."""
    email_id = await _store(
        agent,
        gmail_id="focus-1",
        subject="Please review the notes",
        body="Can you look at this when you have a moment?",
    )
    await agent.preferences.apply_command("quiet 00:00-00:00")
    await agent.preferences.set_extra("focus_until", (utcnow() + timedelta(hours=2)).isoformat())
    plans = await agent.notifier.claim_ready()
    assert all(plan.email_id != email_id for plan in plans)
    preview = await agent.replies.stage_body(email_id, 42, "The file is attached.")
    assert preview.approval_id
    assert preview.body == "The file is attached."
    rendered = agent.templates.render("Hello {name}", {"name": "Priya"})
    assert rendered == "Hello Priya"
