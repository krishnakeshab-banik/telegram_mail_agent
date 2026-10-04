"""Natural-language questions and owner-requested actions."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.intent_router import IntentRouter
from app.ai.schemas import IntentSchema, SearchFiltersSchema
from app.ai.searcher import MailSearcher
from app.constants import IntentName
from app.db.base import session_scope
from app.db.models.conversation import ConversationTurn
from app.db.models.email import EmailMessage
from app.db.repositories.email_repository import EmailRepository
from app.db.repositories.state_repository import ConversationRepository
from app.services.briefing_service import BriefingService, Digest
from app.services.contact_service import ContactService
from app.services.extraction import resolve_when
from app.services.followup_service import FollowUpService
from app.services.preference_service import PreferenceService
from app.services.reminder_service import ReminderService
from app.services.task_service import TaskService
from app.utils.time import parse_iso, to_local, utcnow


@dataclass(frozen=True)
class QueryResult:
    """What the bot should show after a plain-text message."""

    text: str
    kind: str
    email_id: int | None = None
    tone: str = ""


class QueryService:
    """Route owner text to search, lists, reminders, or a reply draft."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        router: IntentRouter,
        searcher: MailSearcher,
        preferences: PreferenceService,
        contacts: ContactService,
        tasks: TaskService,
        followups: FollowUpService,
        briefing: BriefingService,
        reminders: ReminderService,
    ) -> None:
        """Store collaborators.

        Args:
            session_factory: Database session factory.
            router: Intent model. Only owner text is passed to it.
            searcher: Answer composer.
            preferences: Preference commands and timezone.
            contacts: VIP and mute commands.
            tasks: Task list and reminder creation.
            followups: Follow-up list.
            briefing: Briefing and wrap-up text sources.
            reminders: Reminder scheduler.
        """
        self._sessions = session_factory
        self._router = router
        self._searcher = searcher
        self._preferences = preferences
        self._contacts = contacts
        self._tasks = tasks
        self._followups = followups
        self._briefing = briefing
        self._reminders = reminders

    async def handle(self, telegram_user_id: int, text: str) -> QueryResult:
        """Interpret one owner message.

        Args:
            telegram_user_id: Allowlisted user id.
            text: Message text. This is the only text that can request an action.

        Returns:
            A result the handler can format.
        """
        preference = await self._preferences.apply_command(text)
        if preference:
            return QueryResult(preference, "text")
        contact = await self._contacts.apply_command(text)
        if contact:
            return QueryResult(contact, "text")
        history = await self._history(telegram_user_id)
        intent = await self._router.route(text, history)
        await self._remember(telegram_user_id, "user", text)
        result = await self._dispatch(intent, text)
        await self._remember(telegram_user_id, "assistant", result.text[:1000])
        return result

    async def _dispatch(self, intent: IntentSchema, text: str) -> QueryResult:
        if intent.intent == IntentName.SEARCH:
            return await self._search(text, intent)
        if intent.intent == IntentName.REMIND:
            return await self._remind(intent)
        if intent.intent == IntentName.LIST_TASKS:
            return QueryResult(
                _lines("Open tasks", [task.title for task in await self._tasks.list_open()]), "text"
            )
        if intent.intent == IntentName.LIST_DEADLINES:
            return await self._search(text, intent)
        if intent.intent == IntentName.BRIEF:
            return QueryResult("", "digest")
        if intent.intent == IntentName.WRAPUP:
            return QueryResult("", "wrapup")
        if intent.intent == IntentName.FOLLOWUPS:
            items = [
                item.subject or item.counterpart_email for item in await self._followups.list_open()
            ]
            return QueryResult(_lines("Follow-ups", items), "text")
        if intent.intent == IntentName.CALENDAR:
            return QueryResult(intent.calendar_window, "calendar")
        if intent.intent == IntentName.DRAFT_REPLY:
            email_id = await self._find_target(intent.reply_target)
            if email_id is None:
                return QueryResult("I could not find that email to reply to.", "text")
            return QueryResult("", "draft", email_id=email_id, tone=intent.tone)
        return QueryResult(
            intent.reply_text or "I can search mail, list tasks, or draft a reply.", "text"
        )

    async def _search(self, text: str, intent: IntentSchema) -> QueryResult:
        prefs = await self._preferences.get()
        filters = intent.search
        if intent.intent == IntentName.LIST_DEADLINES:
            filters = SearchFiltersSchema(
                date_from=_iso(utcnow()), date_to=_iso(utcnow() + timedelta(days=7))
            )
        messages = await self._query(filters, prefs.timezone)
        records = [_record(message) for message in messages]
        answer = await self._searcher.answer(text, intent, records)
        return QueryResult(answer.answer, "text")

    async def _query(self, filters: SearchFiltersSchema, timezone_name: str) -> list[EmailMessage]:
        async with session_scope(self._sessions) as session:
            return await EmailRepository(session).search(
                sender=filters.sender or None,
                keywords=[item for item in filters.keywords if item],
                category=filters.category or None,
                min_importance=filters.min_importance or None,
                date_from=_bound(filters.date_from, timezone_name, end=False),
                date_to=_bound(filters.date_to, timezone_name, end=True),
                unread_only=filters.unread_only,
                limit=filters.limit,
            )

    async def _remind(self, intent: IntentSchema) -> QueryResult:
        prefs = await self._preferences.get()
        title = intent.reminder_text or "Reminder"
        due = resolve_when(intent.reminder_when, prefs.timezone, utcnow())
        task_id = await self._tasks.add(title=title, due_at=due, email_id=None, source="telegram")
        if due is not None:
            await self._reminders.schedule(
                target_type="task",
                target_id=task_id,
                due_at=due,
                lead_minutes=prefs.reminder_leads,
            )
        return QueryResult(f"Reminder saved: {title}", "text")

    async def _find_target(self, target: str) -> int | None:
        if not target:
            return None
        async with session_scope(self._sessions) as session:
            rows = await EmailRepository(session).search(
                sender=target,
                keywords=[],
                category=None,
                min_importance=None,
                date_from=None,
                date_to=None,
                unread_only=False,
                limit=1,
            )
        return rows[0].id if rows else None

    async def _history(self, telegram_user_id: int) -> list[tuple[str, str]]:
        async with session_scope(self._sessions) as session:
            turns = await ConversationRepository(session).recent(telegram_user_id)
        return [(turn.role, turn.content) for turn in turns]

    async def _remember(self, telegram_user_id: int, role: str, content: str) -> None:
        async with session_scope(self._sessions) as session:
            await ConversationRepository(session).add(
                ConversationTurn(
                    telegram_user_id=telegram_user_id, role=role, content=content[:2000]
                )
            )

    async def morning(self) -> Digest:
        """Return the morning digest for command handlers."""
        return await self._briefing.morning()

    async def wrapup(self) -> Digest:
        """Return the evening digest for command handlers."""
        return await self._briefing.wrapup()


def _lines(title: str, rows: list[str]) -> str:
    if not rows:
        return f"{title}: nothing pending."
    body = "\n".join(f"- {row}" for row in rows[:12])
    return f"{title}\n{body}"


def _record(message: EmailMessage) -> str:
    return f"Subject: {message.subject}\nFrom: {message.sender_name} {message.sender_email}\n{message.snippet or message.body_text[:400]}"


def _bound(value: str, timezone_name: str, *, end: bool) -> datetime | None:
    if not value:
        return None
    parsed = parse_iso(value, timezone_name)
    if parsed is None:
        return None
    if end and len(value) == 10:
        local = to_local(parsed, timezone_name).replace(hour=23, minute=59)
        return local.astimezone(parsed.tzinfo)
    return parsed


def _iso(moment: datetime) -> str:
    return moment.date().isoformat()
