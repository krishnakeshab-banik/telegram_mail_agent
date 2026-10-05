"""Import every model so metadata is complete for Alembic."""

from app.db.models.agent_state import AgentState
from app.db.models.analysis import EmailAnalysis
from app.db.models.approval import Approval
from app.db.models.attachment import Attachment
from app.db.models.audit_log import AuditLog
from app.db.models.calendar_event import CalendarEvent
from app.db.models.contact import Contact
from app.db.models.conversation import ConversationTurn
from app.db.models.deadline import Deadline
from app.db.models.draft import DraftReply
from app.db.models.email import EmailMessage
from app.db.models.email_folder_link import EmailFolderLink
from app.db.models.folder import Folder
from app.db.models.followup import FollowUp
from app.db.models.job_error import JobError
from app.db.models.oauth_state import OAuthState
from app.db.models.oauth_token import OAuthToken
from app.db.models.opportunity_item import OpportunityItem
from app.db.models.otp_entry import OtpEntry
from app.db.models.pending_interaction import PendingInteraction
from app.db.models.preference import Preference
from app.db.models.reminder import Reminder
from app.db.models.reply_template import ReplyTemplate
from app.db.models.style_note import StyleNote
from app.db.models.sync_state import SyncState
from app.db.models.task import Task
from app.db.models.user import User

__all__ = [
    "AgentState",
    "Approval",
    "Attachment",
    "AuditLog",
    "CalendarEvent",
    "Contact",
    "ConversationTurn",
    "Deadline",
    "DraftReply",
    "EmailAnalysis",
    "EmailFolderLink",
    "EmailMessage",
    "Folder",
    "OpportunityItem",
    "OtpEntry",
    "FollowUp",
    "JobError",
    "OAuthState",
    "OAuthToken",
    "PendingInteraction",
    "Preference",
    "Reminder",
    "ReplyTemplate",
    "StyleNote",
    "SyncState",
    "Task",
    "User",
]
