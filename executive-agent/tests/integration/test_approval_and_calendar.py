"""Approval gating for replies and calendar creates."""

from app.ai.schemas import DraftSchema
from app.db.base import session_scope
from app.db.models.calendar_event import CalendarEvent
from app.db.repositories.approval_repository import ApprovalRepository
from app.db.repositories.calendar_repository import CalendarEventRepository
from app.services.container import Container
from app.utils.time import utcnow


class _Drafter:
    async def draft(self, **_kwargs: object) -> DraftSchema:
        return DraftSchema(body="Thanks, I will take a look.", tone_used="direct")


async def test_reply_is_not_sent_until_approval(agent: Container) -> None:
    inserted = await agent.sync.sync_inbox()
    await agent.pipeline.process_pending()
    agent.replies._drafter = _Drafter()  # type: ignore[assignment]
    preview = await agent.replies.create_preview(inserted[0], 42)
    before = agent.sync._mailbox._outbox_path  # type: ignore[attr-defined]
    assert not before.exists() or before.read_text(encoding="utf-8").strip() == ""
    result = await agent.approvals.approve(preview.approval_id)
    assert "Sent reply" in result
    assert "demo-sent" in before.read_text(encoding="utf-8")


async def test_new_mail_is_sent_only_after_approval(agent: Container) -> None:
    """A composed email stays in the preview until the owner approves it."""
    import base64
    import json

    preview = await agent.replies.stage_compose(
        recipient="priya@example.com",
        subject="Invoice",
        body="Hi,\n\nPlease share the invoice by Friday.\n\nThanks,",
        instruction="share the invoice by Friday",
        tone="direct",
        telegram_user_id=42,
    )
    outbox = agent.sync._mailbox._outbox_path  # type: ignore[attr-defined]
    assert not outbox.exists() or outbox.read_text(encoding="utf-8").strip() == ""
    result = await agent.approvals.approve(preview.approval_id)
    assert result.startswith("Sent mail")
    entry = json.loads(outbox.read_text(encoding="utf-8").splitlines()[-1])
    decoded = base64.urlsafe_b64decode(entry["raw"]).decode("utf-8")
    assert "priya@example.com" in decoded
    assert "Invoice" in decoded
    assert entry["threadId"] == ""


async def test_expired_approval_cannot_send(agent: Container) -> None:
    inserted = await agent.sync.sync_inbox()
    agent.replies._drafter = _Drafter()  # type: ignore[assignment]
    preview = await agent.replies.create_preview(inserted[0], 42)
    async with session_scope(agent.sessions) as session:
        approval = await ApprovalRepository(session).get(preview.approval_id)
        assert approval is not None
        approval.expires_at = utcnow()
    import pytest
    from app.exceptions import ApprovalExpiredError

    with pytest.raises(ApprovalExpiredError):
        await agent.approvals.approve(preview.approval_id)


async def test_calendar_event_is_created_only_after_approval(agent: Container) -> None:
    async with session_scope(agent.sessions) as session:
        event = await CalendarEventRepository(session).add(
            CalendarEvent(
                title="Design review",
                start_at=utcnow(),
                end_at=utcnow(),
                timezone_name="Asia/Kolkata",
                status="proposed",
            )
        )
        event_id = event.id
    approval_id, _warning = await agent.calendar.request_create(event_id, 42, (30,))
    stored = (
        agent.calendar._calendar._path.read_text(encoding="utf-8")
        if agent.calendar._calendar._path.exists()
        else "[]"
    )  # type: ignore[attr-defined]
    assert stored in {"", "[]"} or "Design review" not in stored
    result = await agent.approvals.approve(approval_id)
    assert "Created calendar event" in result
    created = agent.calendar._calendar._path.read_text(encoding="utf-8")  # type: ignore[attr-defined]
    assert "Design review" in created
