"""Enums, category names, and Telegram callback prefixes."""

from enum import StrEnum


class Category(StrEnum):
    """Email categories produced by the classifier."""

    WORK = "work"
    ACADEMICS = "academics"
    MEETINGS = "meetings"
    FINANCE = "finance"
    PERSONAL = "personal"
    NEWSLETTERS = "newsletters"
    NOTIFICATIONS = "notifications"
    OTHER = "other"


class Urgency(StrEnum):
    """How quickly an email needs attention."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ApprovalStatus(StrEnum):
    """Lifecycle of a user confirmation gate."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    FAILED = "failed"


class ApprovalAction(StrEnum):
    """Mutating actions that require an explicit confirmation."""

    SEND_EMAIL = "send_email"
    CREATE_EVENT = "create_event"
    UPDATE_EVENT = "update_event"
    DELETE_EVENT = "delete_event"
    APPLY_LABEL = "apply_label"


class TaskStatus(StrEnum):
    """Open, finished, or deferred work items."""

    OPEN = "open"
    DONE = "done"
    SNOOZED = "snoozed"


class FollowUpStatus(StrEnum):
    """State of a reply-needed or awaiting-response item."""

    OPEN = "open"
    SNOOZED = "snoozed"
    DISMISSED = "dismissed"
    DONE = "done"


class FollowUpDirection(StrEnum):
    """Whether we owe a reply or we are waiting on someone else."""

    INBOUND_NEEDS_REPLY = "inbound_needs_reply"
    OUTBOUND_AWAITING = "outbound_awaiting"


class RelationshipType(StrEnum):
    """How a sender relates to the user."""

    UNKNOWN = "unknown"
    COLLEAGUE = "colleague"
    MANAGER = "manager"
    PROFESSOR = "professor"
    CLIENT = "client"
    FRIEND = "friend"
    FAMILY = "family"
    VENDOR = "vendor"
    AUTOMATED = "automated"


class EmailDirection(StrEnum):
    """Whether a stored message was received or sent."""

    INBOUND = "inbound"
    OUTBOUND = "outbound"


class NotificationStatus(StrEnum):
    """Delivery state used to avoid duplicate Telegram alerts."""

    NONE = "none"
    CLAIMED = "claimed"
    SENT = "sent"
    HELD = "held"
    SKIPPED = "skipped"


class CalendarEventStatus(StrEnum):
    """Local lifecycle of a detected or created event."""

    PROPOSED = "proposed"
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    IGNORED = "ignored"


class ReminderStatus(StrEnum):
    """Whether a reminder is waiting, sent, or cancelled."""

    PENDING = "pending"
    SENT = "sent"
    CANCELLED = "cancelled"


class PendingKind(StrEnum):
    """What the next free-text message should be applied to."""

    EDIT_DRAFT = "edit_draft"
    EDIT_EVENT = "edit_event"


class IntentName(StrEnum):
    """Actions the intent router may request from a Telegram message."""

    SEARCH = "search"
    REMIND = "remind"
    LIST_TASKS = "list_tasks"
    LIST_DEADLINES = "list_deadlines"
    BRIEF = "brief"
    FOLLOWUPS = "followups"
    CALENDAR = "calendar"
    DRAFT_REPLY = "draft_reply"
    WRAPUP = "wrapup"
    CHITCHAT = "chitchat"


class CallbackPrefix(StrEnum):
    """Short prefixes stored in inline-button callback data."""

    DRAFT = "drf"
    SUMMARIZE = "sum"
    ADD_CALENDAR = "cal"
    CREATE_TASK = "tsk"
    MARK_DONE = "mdn"
    MUTE = "mut"
    NOT_IMPORTANT = "nim"
    SEND = "snd"
    EDIT = "edt"
    REGENERATE = "rgn"
    SHORTER = "shr"
    FORMAL = "frm"
    FRIENDLY = "frn"
    CANCEL = "cnl"
    IGNORE = "ign"
    SNOOZE_1H = "s1h"
    SNOOZE_TOMORROW = "stm"
    FOLLOWUP_DRAFT = "fdr"
    DISMISS = "dsm"
    CATEGORY = "cat"
    APPROVE_EVENT = "aev"
    EDIT_EVENT = "eev"
    DELETE_EVENT = "dev"
    DONE_TASK = "dtk"
    SNOOZE_TASK_1H = "t1h"
    SNOOZE_TASK_TOMORROW = "ttm"
    PREF_TONE = "ptn"
    PREF_LABELS = "plb"
    PREF_THRESHOLD = "pth"
    FOLDER_PAGE = "fld"
    OPP_STATUS = "ops"
    OTP_REVEAL = "otp"
    REPLY_VARIANT = "rv"
    QUICK_REPLY = "qk"


# Scopes are fixed at consent time. gmail.modify is required to attach labels
# to messages. The client never calls trash, delete, or settings endpoints.
GOOGLE_SCOPES: tuple[str, ...] = (
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar.events",
)

GMAIL_LABEL_PREFIX = "Agent"
URGENCY_BADGES: dict[str, str] = {
    Urgency.LOW: "LOW",
    Urgency.MEDIUM: "MED",
    Urgency.HIGH: "HIGH",
    Urgency.CRITICAL: "CRIT",
}
MAX_CALLBACK_BYTES = 64
DEFAULT_CATEGORY_NOTIFY: dict[str, bool] = {
    Category.WORK: True,
    Category.ACADEMICS: True,
    Category.MEETINGS: True,
    Category.FINANCE: True,
    Category.PERSONAL: True,
    Category.NEWSLETTERS: False,
    Category.NOTIFICATIONS: False,
    Category.OTHER: True,
}


FOLDER_SPECS: tuple[tuple[str, str, str], ...] = (
    ("meets", "Meets", "instant"),
    ("deadlines", "Deadlines", "digest"),
    ("tasks", "Tasks", "digest"),
    ("waiting", "Waiting", "digest"),
    ("important", "Important", "instant"),
    ("jobs", "Jobs", "digest"),
    ("hackathons", "Hackathons", "digest"),
    ("events", "Events", "digest"),
    ("scholarships", "Scholarships", "digest"),
    ("opportunities", "Opportunities", "digest"),
    ("bills", "Bills", "digest"),
    ("orders", "Orders", "digest"),
    ("travel", "Travel", "digest"),
    ("finance", "Finance", "digest"),
    ("academics", "Academics", "digest"),
    ("otps", "OTPs", "mute"),
    ("newsletters", "Newsletters", "mute"),
    ("spam", "Spam", "instant"),
    ("filtered", "Filtered", "mute"),
    ("vip", "VIP", "instant"),
    ("saved", "Saved", "mute"),
    ("archive", "Archive", "mute"),
)


def callback_data(prefix: CallbackPrefix, *parts: object) -> str:
    """Build Telegram callback data and reject values over the 64-byte limit.

    Args:
        prefix: Registered callback prefix.
        *parts: Identifier segments appended after the prefix.

    Returns:
        Colon-joined callback data.
    """
    rendered = ":".join([prefix.value, *[str(part) for part in parts]])
    if len(rendered.encode("utf-8")) > MAX_CALLBACK_BYTES:
        raise ValueError(f"Callback data exceeds {MAX_CALLBACK_BYTES} bytes.")
    return rendered
