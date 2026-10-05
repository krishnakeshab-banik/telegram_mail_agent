"""Decide which processed emails deserve an instant Telegram alert."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.constants import NotificationStatus, Urgency
from app.db.base import session_scope
from app.db.models.analysis import EmailAnalysis
from app.db.models.email import EmailMessage
from app.db.repositories.analysis_repository import AnalysisRepository
from app.db.repositories.common import loads
from app.db.repositories.email_repository import EmailRepository
from app.services.contact_service import ContactService
from app.services.folder_rules import looks_like_otp
from app.services.preference_service import PreferenceService, UserPreferences
from app.utils.time import in_quiet_hours, utcnow


@dataclass(frozen=True)
class AlertPlan:
    """Facts the formatter needs for one instant alert."""

    email_id: int
    sender_name: str
    sender_email: str
    subject: str
    summary: str
    category: str
    urgency: str
    deadline_lines: list[str]
    task_lines: list[str]
    meeting_line: str
    has_meeting: bool


class Notifier:
    """Apply quiet hours, category settings, and the importance threshold."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        preferences: PreferenceService,
        contacts: ContactService,
    ) -> None:
        """Store collaborators.

        Args:
            session_factory: Database session factory.
            preferences: Notification settings.
            contacts: Mute and VIP flags.
        """
        self._sessions = session_factory
        self._preferences = preferences
        self._contacts = contacts

    async def claim_ready(self) -> list[AlertPlan]:
        """Claim alerts that should be sent now.

        Returns:
            Plans the caller should deliver. Claimed rows are not returned twice.
        """
        prefs = await self._preferences.get()
        async with session_scope(self._sessions) as session:
            emails = EmailRepository(session)
            waiting = await emails.list_by_notification_status(NotificationStatus.NONE)
            waiting.extend(await emails.list_by_notification_status(NotificationStatus.HELD))
            pairs = []
            for message in waiting:
                analysis = await AnalysisRepository(session).get_by_email(message.id)
                if analysis is not None:
                    pairs.append((message, analysis))
        plans: list[AlertPlan] = []
        for message, analysis in pairs:
            decision = await self._decide(message, analysis, prefs)
            await self._apply_decision(message.id, decision, plans, message, analysis)
        return plans

    async def _apply_decision(
        self,
        email_id: int,
        decision: str,
        plans: list[AlertPlan],
        message: EmailMessage,
        analysis: EmailAnalysis,
    ) -> None:
        async with session_scope(self._sessions) as session:
            emails = EmailRepository(session)
            if decision == "skip":
                await emails.skip_notification(email_id)
            elif decision == "hold":
                await emails.hold_notification(email_id)
            elif await emails.claim_notification(email_id):
                plans.append(_plan(message, analysis))

    async def skip(self, email_id: int) -> None:
        """Stop alerts for one message."""
        async with session_scope(self._sessions) as session:
            await EmailRepository(session).skip_notification(email_id)

    async def mark_sent(self, email_id: int) -> None:
        """Record a successful delivery."""
        async with session_scope(self._sessions) as session:
            await EmailRepository(session).mark_notified(email_id, utcnow())

    async def release(self, email_id: int) -> None:
        """Return a claimed alert to the held queue after a send failure."""
        async with session_scope(self._sessions) as session:
            await EmailRepository(session).release_claim(email_id)

    async def _decide(
        self, message: EmailMessage, analysis: EmailAnalysis, prefs: UserPreferences
    ) -> str:
        if looks_like_otp(message.subject, message.body_text):
            return "skip"
        if await self._preferences.focus_active():
            phishing = analysis.summary.lower().startswith("suspicious")
            if analysis.urgency == Urgency.CRITICAL or phishing:
                return "send"
            return "hold"
        contact = await self._contacts.get(message.sender_email)
        if contact is not None and contact.is_muted:
            return "skip"
        if not prefs.category_notify.get(analysis.category, True):
            return "skip"
        urgent = analysis.urgency in {Urgency.HIGH, Urgency.CRITICAL}
        if analysis.importance_score < prefs.importance_threshold and not urgent:
            return "skip"
        phishing = analysis.summary.lower().startswith("suspicious")
        if analysis.urgency == Urgency.CRITICAL or phishing:
            return "send"
        if in_quiet_hours(utcnow(), prefs.timezone, prefs.quiet_start, prefs.quiet_end):
            return "hold"
        return "send"


def _plan(message: EmailMessage, analysis: EmailAnalysis) -> AlertPlan:
    deadlines = loads(analysis.deadlines_json, [])
    actions = loads(analysis.action_items_json, [])
    meeting = loads(analysis.meeting_json, {})
    deadline_lines = [str(item.get("title", "")) for item in deadlines if isinstance(item, dict)]
    task_lines = [str(item.get("task", "")) for item in actions if isinstance(item, dict)]
    meeting_title = str(meeting.get("title", "")) if isinstance(meeting, dict) else ""
    return AlertPlan(
        email_id=message.id,
        sender_name=message.sender_name,
        sender_email=message.sender_email,
        subject=message.subject,
        summary=analysis.summary,
        category=analysis.category,
        urgency=analysis.urgency,
        deadline_lines=[line for line in deadline_lines if line][:3],
        task_lines=[line for line in task_lines if line][:3],
        meeting_line=meeting_title,
        has_meeting=bool(meeting_title),
    )
