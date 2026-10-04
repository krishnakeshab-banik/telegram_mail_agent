"""Repository exports."""

from app.db.repositories.analysis_repository import AnalysisRepository
from app.db.repositories.approval_repository import ApprovalRepository
from app.db.repositories.attachment_repository import AttachmentRepository
from app.db.repositories.audit_repository import AuditRepository
from app.db.repositories.calendar_repository import CalendarEventRepository
from app.db.repositories.contact_repository import ContactRepository
from app.db.repositories.deadline_repository import DeadlineRepository
from app.db.repositories.email_repository import EmailRepository
from app.db.repositories.followup_repository import FollowUpRepository
from app.db.repositories.preference_repository import PreferenceRepository
from app.db.repositories.reminder_repository import ReminderRepository
from app.db.repositories.state_repository import (
    AgentStateRepository,
    ConversationRepository,
    DraftRepository,
    JobErrorRepository,
    OAuthRepository,
    PendingInteractionRepository,
    StyleNoteRepository,
    SyncStateRepository,
)
from app.db.repositories.task_repository import TaskRepository

__all__ = [
    "AgentStateRepository",
    "AnalysisRepository",
    "ApprovalRepository",
    "AttachmentRepository",
    "AuditRepository",
    "CalendarEventRepository",
    "ContactRepository",
    "ConversationRepository",
    "DeadlineRepository",
    "DraftRepository",
    "EmailRepository",
    "FollowUpRepository",
    "JobErrorRepository",
    "OAuthRepository",
    "PendingInteractionRepository",
    "PreferenceRepository",
    "ReminderRepository",
    "StyleNoteRepository",
    "SyncStateRepository",
    "TaskRepository",
]
