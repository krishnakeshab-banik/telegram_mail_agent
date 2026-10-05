"""Compose a mailbox answer from records the application already retrieved."""

from app.ai.gemini_client import GeminiClient
from app.ai.prompt_loader import load_prompt
from app.ai.schemas import AnswerSchema, IntentSchema
from app.utils.security import wrap_untrusted


class MailSearcher:
    """Turn retrieved rows into an answer. It cannot send or mutate anything."""

    def __init__(self, gemini: GeminiClient) -> None:
        """Store the shared Gemini client.

        Args:
            gemini: Shared Gemini wrapper. The model chain lives on the client.
        """
        self._gemini = gemini

    async def answer(self, question: str, intent: IntentSchema, records: list[str]) -> AnswerSchema:
        """Answer a question from retrieved email excerpts.

        Args:
            question: Owner's question.
            intent: Structured intent already chosen by the router.
            records: Short excerpts prepared by the service. Treated as untrusted.

        Returns:
            Validated answer. Falls back to a plain listing when Gemini is off.
        """
        if not self._gemini.enabled:
            return _fallback(records)
        wrapped = "\n".join(
            wrap_untrusted(f"record_{index}", record[:700])
            for index, record in enumerate(records, start=1)
        )
        user_prompt = "\n".join(
            [
                wrap_untrusted("owner_question", question[:1000]),
                f"Intent: {intent.intent.value}",
                wrapped or wrap_untrusted("records", "none"),
            ]
        )
        payload = await self._gemini.generate_json(
            system_prompt=load_prompt("compose_answer"),
            user_prompt=user_prompt,
            schema=AnswerSchema,
        )
        return AnswerSchema.model_validate(payload)


def _fallback(records: list[str]) -> AnswerSchema:
    if not records:
        return AnswerSchema(answer="I could not find matching email in the local mailbox.")
    preview = "\n".join(f"- {record[:180]}" for record in records[:5])
    subjects = [record.split("\n", 1)[0][:80] for record in records[:5]]
    return AnswerSchema(answer=preview, referenced_subjects=subjects)
