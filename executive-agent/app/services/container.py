"""Composition root. Constructs services and registers approval executors."""

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.ai.classifier import EmailClassifier
from app.ai.drafter import ReplyDrafter
from app.ai.gemini_client import GeminiClient
from app.ai.intent_router import IntentRouter
from app.ai.searcher import MailSearcher
from app.ai.summarizer import Summarizer
from app.bot.sender import TelegramSender
from app.config import Settings
from app.constants import ApprovalAction
from app.db.base import create_engine, create_session_factory
from app.google.auth import GoogleAuth
from app.google.calendar_client import CalendarClient, CalendarGateway, DemoCalendarClient
from app.google.gmail_client import DemoGmailClient, GmailClient, MailboxClient
from app.services.account_service import AccountService
from app.services.approval_service import ApprovalService
from app.services.attachment_service import AttachmentService
from app.services.audit_service import AuditService
from app.services.briefing_service import BriefingService
from app.services.calendar_service import CalendarService
from app.services.contact_service import ContactService
from app.services.email_pipeline import EmailPipeline
from app.services.folder_service import FolderService
from app.services.followup_service import FollowUpService
from app.services.inbox_service import InboxService
from app.services.label_service import LabelService
from app.services.notifier import Notifier
from app.services.otp_vault import OtpVault
from app.services.preference_service import PreferenceService
from app.services.query_service import QueryService
from app.services.reminder_service import ReminderService
from app.services.reply_service import ReplyService
from app.services.reply_suggestion_service import ReplySuggestionService
from app.services.sync_service import SyncService
from app.services.task_service import TaskService
from app.services.template_service import TemplateService
from app.services.thread_service import ThreadService
from app.services.user_service import UserService


@dataclass
class Container:
    """Wired services for the bot and the scheduler."""

    settings: Settings
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    sender: TelegramSender
    preferences: PreferenceService
    contacts: ContactService
    audit: AuditService
    approvals: ApprovalService
    tasks: TaskService
    reminders: ReminderService
    followups: FollowUpService
    sync: SyncService
    pipeline: EmailPipeline
    notifier: Notifier
    calendar: CalendarService
    attachments: AttachmentService
    replies: ReplyService
    briefing: BriefingService
    queries: QueryService
    inbox: InboxService
    labels: LabelService
    threads: ThreadService
    gemini: GeminiClient
    folders: FolderService
    otp: OtpVault
    suggestions: ReplySuggestionService
    templates: TemplateService
    users: UserService
    accounts: AccountService
    owner_id: int = 0

    async def aclose(self) -> None:
        """Close network clients and the database engine."""
        await self.sync._mailbox.aclose()
        await self.calendar._calendar.aclose()
        await self.engine.dispose()


def build_container(settings: Settings, *, data_dir: Path | None = None) -> Container:
    """Construct the object graph.

    Args:
        settings: Process settings.
        data_dir: Directory for demo outbox and calendar files.

    Returns:
        Ready container. Callers still need to bind the Telegram sender.
    """
    sender = TelegramSender()
    root = data_dir or Path("data")
    root.mkdir(parents=True, exist_ok=True)
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    gemini = GeminiClient(
        settings.gemini_api_key,
        requests_per_minute=settings.gemini_requests_per_minute,
        models=settings.model_chain,
    )
    auth = GoogleAuth(sessions, settings)
    mailbox, calendar_gateway = _gateways(settings, auth, root)
    sync = SyncService(sessions, mailbox)
    otp = OtpVault(sessions, settings.fernet_key)
    demo = settings.app_mode == "demo"
    classifier = EmailClassifier(gemini, allow_offline=demo)
    summarizer = Summarizer(gemini)
    preferences = PreferenceService(sessions, settings, gemini)
    contacts = ContactService(sessions)
    folders = FolderService(sessions, contacts, otp, preferences)
    audit = AuditService(sessions)
    approvals = ApprovalService(sessions, settings, audit)
    tasks = TaskService(sessions)
    reminders = ReminderService(sessions)
    followups = FollowUpService(sessions)
    calendar = CalendarService(sessions, calendar_gateway, approvals, reminders)
    briefing = BriefingService(sessions, preferences, tasks, followups, calendar, summarizer)
    replies = ReplyService(
        sessions,
        mailbox,
        ReplyDrafter(gemini),
        approvals,
        preferences,
        contacts,
        followups,
    )
    labels = LabelService(sessions, mailbox, approvals)
    approvals.register(ApprovalAction.SEND_EMAIL, replies.execute_send)
    approvals.register(ApprovalAction.CREATE_EVENT, calendar.execute_create)
    approvals.register(ApprovalAction.UPDATE_EVENT, calendar.execute_update)
    approvals.register(ApprovalAction.DELETE_EVENT, calendar.execute_delete)
    approvals.register(ApprovalAction.APPLY_LABEL, labels.execute)
    pipeline = EmailPipeline(sessions, classifier, contacts, preferences, reminders)
    users = UserService(sessions, settings)
    accounts = AccountService(sessions, settings, auth, sync, pipeline, preferences, users)

    async def _notify(chat_id: int, text: str, buttons: object) -> None:
        from app.bot.formatters import plain
        from app.bot.keyboards.signup import markup

        await sender.send_text(chat_id, plain(text), markup(buttons))

    accounts.bind_notifier(_notify)
    container = Container(
        settings=settings,
        engine=engine,
        sessions=sessions,
        sender=sender,
        preferences=preferences,
        contacts=contacts,
        audit=audit,
        approvals=approvals,
        tasks=tasks,
        reminders=reminders,
        followups=followups,
        sync=sync,
        pipeline=pipeline,
        notifier=Notifier(sessions, preferences, contacts),
        calendar=calendar,
        attachments=AttachmentService(
            sessions, mailbox, summarizer, max_bytes=settings.max_attachment_bytes
        ),
        replies=replies,
        briefing=briefing,
        queries=QueryService(
            sessions,
            IntentRouter(gemini, allow_local_fallback=demo),
            MailSearcher(gemini),
            preferences,
            contacts,
            tasks,
            followups,
            briefing,
            reminders,
        ),
        inbox=InboxService(sessions, preferences),
        labels=labels,
        threads=ThreadService(sessions, summarizer),
        gemini=gemini,
        folders=folders,
        otp=otp,
        suggestions=ReplySuggestionService(),
        templates=TemplateService(sessions),
        users=users,
        accounts=accounts,
    )

    async def _tell_admins(text: str) -> None:
        from app.services.admin_alert import alert_admins

        await alert_admins(container, text)

    gemini.set_chain_handler(_tell_admins)
    return container


def _gateways(
    settings: Settings, auth: GoogleAuth, root: Path
) -> tuple[MailboxClient, CalendarGateway]:
    if settings.app_mode == "demo":
        return (
            DemoGmailClient(Path(settings.fixture_dir), root / "demo_outbox.jsonl"),
            DemoCalendarClient(root / "demo_calendar.json"),
        )
    return (
        GmailClient(auth, requests_per_minute=settings.google_requests_per_minute),
        CalendarClient(auth, requests_per_minute=settings.google_requests_per_minute),
    )
