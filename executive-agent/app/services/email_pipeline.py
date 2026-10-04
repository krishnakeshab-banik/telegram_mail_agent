"""Classify a stored email once and persist everything derived from it."""

import json
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.classifier import EmailClassifier
from app.ai.schemas import EmailClassification
from app.db.base import session_scope
from app.db.models.analysis import EmailAnalysis
from app.db.models.contact import Contact
from app.db.repositories.analysis_repository import AnalysisRepository
from app.db.repositories.common import loads
from app.db.repositories.email_repository import EmailRepository
from app.db.repositories.state_repository import SyncStateRepository
from app.exceptions import GeminiError, QuotaExceededError
from app.services.contact_service import ContactService
from app.services.extraction import store_extractions
from app.services.preference_service import PreferenceService
from app.services.reminder_service import ReminderService
from app.utils.logging import get_logger
from app.utils.time import utcnow

logger = get_logger(__name__)


class EmailPipeline:
    """Run cheap checks first, then one structured model call, then storage."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        classifier: EmailClassifier,
        contacts: ContactService,
        preferences: PreferenceService,
        reminders: ReminderService,
    ) -> None:
        """Store collaborators.

        Args:
            session_factory: Database session factory.
            classifier: Heuristic-or-model classifier.
            contacts: Sender profiles used to personalize importance.
            preferences: Timezone and reminder offsets.
            reminders: Scheduler for extracted due dates.
        """
        self._sessions = session_factory
        self._classifier = classifier
        self._contacts = contacts
        self._preferences = preferences
        self._reminders = reminders

    async def process_pending(self, limit: int = 20) -> list[int]:
        """Classify messages that have been stored but not processed.

        Args:
            limit: Maximum messages to handle in one pass.

        Returns:
            Local ids that were processed in this pass.
        """
        async with session_scope(self._sessions) as session:
            pending = await EmailRepository(session).list_unprocessed(limit)
            identifiers = [item.id for item in pending]
        processed: list[int] = []
        for email_id in identifiers:
            try:
                if await self.process(email_id):
                    processed.append(email_id)
            except (GeminiError, QuotaExceededError) as exc:
                await self._remember_gemini_error(str(exc))
                logger.warning(
                    "email_classification_deferred",
                    email_id=email_id,
                    error_type=type(exc).__name__,
                )
        return processed

    async def process(self, email_id: int) -> bool:
        """Classify one message. A second call is a no-op.

        Args:
            email_id: Local email id.

        Returns:
            True when the message is processed, including when it already was.
        """
        prefs = await self._preferences.get()
        async with session_scope(self._sessions) as session:
            message = await EmailRepository(session).get(email_id)
            if message is None or message.processed_at is not None:
                return message is not None
            if await AnalysisRepository(session).get_by_email(email_id) is not None:
                message.processed_at = utcnow()
                return True
            sender = message.sender_email
            subject = message.subject
            body = message.body_text
            bulk = message.is_bulk
            labels = loads(message.labels, [])
        contact = await self._contacts.get(sender)
        classification, model_name = await self._classifier.classify(
            sender=sender,
            subject=subject,
            body=body,
            headers_summary=",".join(labels) if isinstance(labels, list) else "",
            bulk=bulk and not (contact and contact.is_vip),
        )
        score = _personalize(classification.importance_score, contact)
        classification = classification.model_copy(update={"importance_score": score})
        due_items = await self._persist(email_id, classification, model_name, prefs.timezone)
        for target_type, target_id, due_at in due_items:
            await self._reminders.schedule(
                target_type=target_type,
                target_id=target_id,
                due_at=due_at,
                lead_minutes=prefs.reminder_leads,
            )
        await self._contacts.observe_message(sender, "", classification.category.value)
        logger.info("email_processed", email_id=email_id, category=classification.category.value)
        return True

    async def _remember_gemini_error(self, message: str) -> None:
        async with session_scope(self._sessions) as session:
            state = await SyncStateRepository(session).get_singleton()
            state.last_gemini_error = message[:400]
            state.updated_at = utcnow()

    async def correct_category(self, email_id: int, category: str) -> None:
        """Store an owner correction, which is a learning signal."""
        async with session_scope(self._sessions) as session:
            analysis = await AnalysisRepository(session).get_by_email(email_id)
            message = await EmailRepository(session).get(email_id)
            if analysis is None or message is None:
                return
            analysis.category = category
            sender = message.sender_email
        await self._contacts.observe_message(sender, "", category)

    async def _persist(
        self,
        email_id: int,
        classification: EmailClassification,
        model_name: str,
        timezone_name: str,
    ) -> list[tuple[str, int, datetime]]:
        from app.db.repositories.deadline_repository import DeadlineRepository
        from app.db.repositories.task_repository import TaskRepository

        due: list[tuple[str, int, datetime]] = []
        async with session_scope(self._sessions) as session:
            message = await EmailRepository(session).get(email_id)
            if message is None:
                return []
            await AnalysisRepository(session).add(_analysis(email_id, classification, model_name))
            task_ids, deadline_ids, _event_id = await store_extractions(
                session, message, classification, timezone_name
            )
            message.processed_at = utcnow()
            for task_id in task_ids:
                task = await TaskRepository(session).get(task_id)
                if task is not None and task.due_at is not None:
                    due.append(("task", task.id, task.due_at))
            for deadline_id in deadline_ids:
                deadline = await DeadlineRepository(session).get(deadline_id)
                if deadline is not None and deadline.due_at is not None:
                    due.append(("deadline", deadline.id, deadline.due_at))
        return [(kind, item_id, moment) for kind, item_id, moment in due]


def _personalize(score: int, contact: Contact | None) -> int:
    if contact is None:
        return score
    adjusted = score
    if contact.is_vip:
        adjusted += 25
    if contact.is_muted:
        adjusted = min(adjusted, 10)
    weighted = round(adjusted * contact.priority_weight)
    return max(0, min(100, weighted))


def _analysis(email_id: int, classification: EmailClassification, model_name: str) -> EmailAnalysis:
    meeting = classification.meeting.model_dump() if classification.meeting.is_present else None
    return EmailAnalysis(
        email_id=email_id,
        category=classification.category.value,
        importance_score=classification.importance_score,
        urgency=classification.urgency.value,
        requires_reply=classification.requires_reply,
        summary=classification.summary,
        sentiment=classification.sentiment[:64],
        action_items_json=json.dumps([item.model_dump() for item in classification.action_items]),
        deadlines_json=json.dumps([item.model_dump() for item in classification.deadlines]),
        meeting_json=json.dumps(meeting) if meeting else "",
        outbound_promise=classification.outbound_promise[:500],
        promise_due=classification.promise_due[:64],
        model_name=model_name[:64],
    )
