"""Email classification. Bulk mail is handled before any model call."""

from app.ai.gemini_client import GeminiClient
from app.ai.prompt_loader import load_prompt
from app.ai.schemas import ActionItemSchema, DeadlineSchema, EmailClassification
from app.constants import Category, Urgency
from app.exceptions import GeminiError
from app.utils.logging import get_logger
from app.utils.security import wrap_untrusted
from app.utils.text import excerpt

logger = get_logger(__name__)
_BODY_LIMIT = 6000


class EmailClassifier:
    """Produce a validated classification for one message."""

    def __init__(self, gemini: GeminiClient, *, allow_offline: bool = False) -> None:
        """Store the model client.

        Args:
            gemini: Shared Gemini wrapper. The model chain lives on the client.
            allow_offline: When demo mode has no API key, use keyword classification.
        """
        self._gemini = gemini
        self._allow_offline = allow_offline

    async def classify(
        self,
        *,
        sender: str,
        subject: str,
        body: str,
        headers_summary: str,
        bulk: bool,
    ) -> tuple[EmailClassification, str]:
        """Classify a message, skipping the model for obvious bulk mail.

        Args:
            sender: Display name and address.
            subject: Subject line, treated as untrusted.
            body: Plain-text body, treated as untrusted.
            headers_summary: Selected header names already judged by code.
            bulk: True when pre-filter heuristics matched.

        Returns:
            Classification and the model name, or "heuristic".
        """
        if bulk:
            return _heuristic(subject, body), "heuristic"
        if not self._gemini.enabled:
            if self._allow_offline:
                return _offline(subject, body), "offline-demo"
            raise GeminiError("GEMINI_API_KEY is required to classify mail.")
        user_prompt = "\n".join(
            [
                wrap_untrusted("sender", sender),
                wrap_untrusted("email_subject", subject),
                wrap_untrusted("headers", headers_summary),
                wrap_untrusted("email_body", body[:_BODY_LIMIT]),
            ]
        )
        payload = await self._gemini.generate_json(
            system_prompt=load_prompt("classify_email"),
            user_prompt=user_prompt,
            schema=EmailClassification,
        )
        logger.info("email_classified", model=self._gemini.last_model)
        return EmailClassification.model_validate(payload), self._gemini.last_model


def _offline(subject: str, body: str) -> EmailClassification:
    """Keyword classification used only when demo mode has no Gemini key."""
    text = f"{subject}\n{body}".lower()
    if any(word in text for word in ("invoice", "payment", "amount due")):
        category, score = Category.FINANCE, 72
    elif any(word in text for word in ("zoom.us", "meet.google.com", "teams.microsoft", "meeting")):
        category, score = Category.MEETINGS, 80
    elif any(word in text for word in ("assignment", "professor", "deadline", "exam")):
        category, score = Category.ACADEMICS, 84
    else:
        category, score = Category.WORK, 64
    meeting = EmailClassification().meeting
    if category == Category.MEETINGS:
        phrase = "next Tuesday at 3pm" if "tuesday" in text else ""
        meeting = meeting.model_copy(
            update={"title": subject or "Meeting", "relative_phrase": phrase, "confidence": 0.7}
        )
    return EmailClassification(
        category=category,
        importance_score=score,
        urgency=Urgency.HIGH if score >= 80 else Urgency.MEDIUM,
        requires_reply=category != Category.FINANCE,
        summary=excerpt(subject or body, 180),
        sentiment="neutral",
        action_items=[ActionItemSchema(task=f"Review: {subject}"[:180])] if score >= 70 else [],
        deadlines=[DeadlineSchema(title=subject, relative_phrase="tomorrow", confidence=0.5)]
        if "deadline" in text
        else [],
        meeting=meeting,
    )


def _heuristic(subject: str, body: str) -> EmailClassification:
    summary_source = subject or excerpt(body, 180)
    return EmailClassification(
        category=Category.NEWSLETTERS,
        importance_score=8,
        urgency=Urgency.LOW,
        requires_reply=False,
        summary=excerpt(summary_source, 180),
        sentiment="neutral",
        meeting=EmailClassification().meeting,
    )
