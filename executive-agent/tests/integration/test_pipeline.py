"""Sync, classification, dedupe, and notification claiming."""

from app.constants import NotificationStatus
from app.db.base import session_scope
from app.db.repositories.analysis_repository import AnalysisRepository
from app.db.repositories.email_repository import EmailRepository
from app.services.container import Container


async def test_sync_is_idempotent_and_pipeline_classifies_once(agent: Container) -> None:
    first = await agent.sync.sync_inbox()
    second = await agent.sync.sync_inbox()
    processed = await agent.pipeline.process_pending()
    again = await agent.pipeline.process_pending()
    assert len(first) == 6
    assert second == []
    assert len(processed) == 6
    assert again == []
    async with session_scope(agent.sessions) as session:
        newsletter = await EmailRepository(session).get_by_gmail_id("msg-newsletter")
        assert newsletter is not None
        analysis = await AnalysisRepository(session).get_by_email(newsletter.id)
    assert analysis is not None
    assert analysis.model_name == "heuristic"
    assert analysis.category == "newsletters"


async def test_important_mail_is_claimed_once(agent: Container) -> None:
    await agent.preferences.apply_command("quiet 00:00-00:00")
    await agent.preferences.remember_chat(42)
    await agent.sync.sync_inbox()
    await agent.pipeline.process_pending()
    first = await agent.notifier.claim_ready()
    second = await agent.notifier.claim_ready()
    assert first
    assert second == []
    async with session_scope(agent.sessions) as session:
        message = await EmailRepository(session).get(first[0].email_id)
    assert message is not None
    assert message.notification_status == NotificationStatus.CLAIMED
