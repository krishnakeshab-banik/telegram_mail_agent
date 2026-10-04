"""Pydantic models for every Gemini JSON response."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.constants import Category, IntentName, Urgency
from app.utils.text import clip_lines


class ActionItemSchema(BaseModel):
    """One task extracted from an email."""

    task: str = ""
    due_date: str = ""
    relative_phrase: str = ""


class DeadlineSchema(BaseModel):
    """One deadline extracted from an email."""

    title: str = ""
    datetime_iso: str = ""
    relative_phrase: str = ""
    confidence: float = Field(default=0.5, ge=0, le=1)


class MeetingSchema(BaseModel):
    """Meeting details. An empty title means no meeting was found."""

    title: str = ""
    start_iso: str = ""
    end_iso: str = ""
    relative_phrase: str = ""
    timezone: str = ""
    location: str = ""
    link: str = ""
    attendees: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0, ge=0, le=1)

    @property
    def is_present(self) -> bool:
        """Return whether the model actually detected a meeting."""
        return bool(self.title.strip()) and self.confidence >= 0.4


class EmailClassification(BaseModel):
    """Structured understanding of a single email."""

    category: Category = Category.OTHER
    importance_score: int = Field(default=0, ge=0, le=100)
    urgency: Urgency = Urgency.LOW
    requires_reply: bool = False
    summary: str = ""
    sentiment: str = ""
    action_items: list[ActionItemSchema] = Field(default_factory=list)
    deadlines: list[DeadlineSchema] = Field(default_factory=list)
    meeting: MeetingSchema = Field(default_factory=MeetingSchema)
    outbound_promise: str = ""
    promise_due: str = ""

    @field_validator("summary")
    @classmethod
    def limit_summary(cls, value: str) -> str:
        """Keep summaries to two lines."""
        return clip_lines(value, 2)[:500]

    @field_validator("category", mode="before")
    @classmethod
    def coerce_category(cls, value: object) -> object:
        """Map unknown categories to other."""
        if isinstance(value, str) and value not in {item.value for item in Category}:
            return Category.OTHER
        return value

    @field_validator("urgency", mode="before")
    @classmethod
    def coerce_urgency(cls, value: object) -> object:
        """Map shorthand urgency labels onto the enum."""
        if value == "med":
            return Urgency.MEDIUM
        if isinstance(value, str) and value not in {item.value for item in Urgency}:
            return Urgency.LOW
        return value


class DraftSchema(BaseModel):
    """A reply body and the tone that produced it."""

    body: str
    tone_used: str = "direct"

    @field_validator("body")
    @classmethod
    def body_required(cls, value: str) -> str:
        """Reject empty drafts."""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Draft body is empty.")
        return cleaned


class ThreadSummarySchema(BaseModel):
    """Compact understanding of a mail thread."""

    participants: list[str] = Field(default_factory=list)
    timeline: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    latest_status: str = ""


class AttachmentSummarySchema(BaseModel):
    """Key facts pulled from an attachment."""

    summary: str = ""
    key_points: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    amounts: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)


class SearchFiltersSchema(BaseModel):
    """Filters produced for a natural-language mailbox question."""

    date_from: str = ""
    date_to: str = ""
    sender: str = ""
    category: str = ""
    min_importance: int = Field(default=0, ge=0, le=100)
    keywords: list[str] = Field(default_factory=list)
    unread_only: bool = False
    limit: int = Field(default=8, ge=1, le=20)


class IntentSchema(BaseModel):
    """What a Telegram message is asking the agent to do."""

    intent: IntentName = IntentName.CHITCHAT
    search: SearchFiltersSchema = Field(default_factory=SearchFiltersSchema)
    reminder_text: str = ""
    reminder_when: str = ""
    reply_target: str = ""
    tone: str = ""
    calendar_window: Literal["today", "week"] = "today"
    reply_text: str = ""

    @field_validator("intent", mode="before")
    @classmethod
    def coerce_intent(cls, value: object) -> object:
        """Fall back to chitchat for unknown intent names."""
        if isinstance(value, str) and value not in {item.value for item in IntentName}:
            return IntentName.CHITCHAT
        return value


class AnswerSchema(BaseModel):
    """Final answer composed from retrieved mail, with no new actions."""

    answer: str
    referenced_subjects: list[str] = Field(default_factory=list)


class StyleNoteSchema(BaseModel):
    """A short observation about how the user edits drafts."""

    note: str = ""


class FocusSchema(BaseModel):
    """One suggested focus line for the daily briefing."""

    focus_line: str = ""
