"""Map a Telegram message to a structured intent. Email text never reaches this router."""

from typing import Literal

from app.ai.gemini_client import GeminiClient
from app.ai.prompt_loader import load_prompt
from app.ai.schemas import IntentSchema, SearchFiltersSchema
from app.constants import IntentName
from app.utils.security import wrap_untrusted

_DEMO_RULES: tuple[tuple[tuple[str, ...], IntentName], ...] = (
    (
        ("what's pending", "whats pending", "pending this week", "deadlines"),
        IntentName.LIST_DEADLINES,
    ),
    (("my tasks", "show tasks", "task list"), IntentName.LIST_TASKS),
    (("follow up", "follow-up", "followups"), IntentName.FOLLOWUPS),
    (("briefing", "brief me"), IntentName.BRIEF),
    (("wrap up", "wrapup"), IntentName.WRAPUP),
    (("calendar", "my meetings", "today's meetings"), IntentName.CALENDAR),
)


class IntentRouter:
    """Interpret owner messages. This is the only path that can request actions."""

    def __init__(self, gemini: GeminiClient, *, allow_local_fallback: bool) -> None:
        """Store the client and whether demo mode may skip the network.

        Args:
            gemini: Shared Gemini wrapper. The model chain lives on the client.
            allow_local_fallback: Use keyword routing when no API key is configured.
        """
        self._gemini = gemini
        self._allow_local_fallback = allow_local_fallback

    async def route(self, text: str, history: list[tuple[str, str]]) -> IntentSchema:
        """Route one owner message.

        Args:
            text: The owner's latest Telegram message.
            history: Prior (role, text) turns from Telegram only.

        Returns:
            Validated intent. Unknown requests become chitchat.
        """
        if not self._gemini.enabled:
            if self._allow_local_fallback:
                return _local_intent(text)
            return IntentSchema(intent=IntentName.CHITCHAT, reply_text="Gemini is not configured.")
        history_text = "\n".join(f"{role}: {content[:500]}" for role, content in history[-6:])
        user_prompt = "\n".join(
            [
                wrap_untrusted("prior_turns", history_text or "none"),
                wrap_untrusted("owner_message", text[:2000]),
            ]
        )
        payload = await self._gemini.generate_json(
            system_prompt=load_prompt("intent_router"),
            user_prompt=user_prompt,
            schema=IntentSchema,
        )
        return IntentSchema.model_validate(payload)


def _local_intent(text: str) -> IntentSchema:
    lowered = text.lower()
    for phrases, intent in _DEMO_RULES:
        if any(phrase in lowered for phrase in phrases):
            window: Literal["today", "week"] = "week" if "week" in lowered else "today"
            return IntentSchema(intent=intent, calendar_window=window)
    if lowered.startswith("remind me"):
        return IntentSchema(
            intent=IntentName.REMIND,
            reminder_text=text.removeprefix("remind me").strip(),
            reminder_when=text,
        )
    return IntentSchema(
        intent=IntentName.SEARCH,
        search=SearchFiltersSchema(keywords=_keywords(text), limit=8),
    )


def _keywords(text: str) -> list[str]:
    stop = {"what", "whats", "what's", "did", "the", "about", "from", "show", "any", "this", "week"}
    words = [word.strip("?.!,").lower() for word in text.split()]
    return [word for word in words if len(word) > 2 and word not in stop][:6]
