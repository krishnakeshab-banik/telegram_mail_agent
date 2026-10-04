"""Reply drafting. The model never sends mail."""

from app.ai.gemini_client import GeminiClient
from app.ai.prompt_loader import load_prompt
from app.ai.schemas import DraftSchema
from app.utils.security import wrap_untrusted

_MESSAGE_LIMIT = 2500


class ReplyDrafter:
    """Generate a reply body from thread context and style notes."""

    def __init__(self, gemini: GeminiClient, model: str) -> None:
        """Store the smart model used for drafting.

        Args:
            gemini: Shared Gemini wrapper.
            model: Smart model name.
        """
        self._gemini = gemini
        self._model = model

    async def draft(
        self,
        *,
        thread_blocks: list[str],
        sender_relationship: str,
        style_notes: str,
        tone: str,
        instruction: str,
    ) -> DraftSchema:
        """Draft a reply for the owner to preview.

        Args:
            thread_blocks: Already truncated message texts, oldest first.
            sender_relationship: Short relationship description.
            style_notes: Learned writing-style notes.
            tone: Requested tone such as formal or friendly.
            instruction: Extra instruction such as "shorter".

        Returns:
            Validated draft.
        """
        wrapped = "\n".join(
            wrap_untrusted(f"thread_message_{index}", block[:_MESSAGE_LIMIT])
            for index, block in enumerate(thread_blocks, start=1)
        )
        user_prompt = "\n".join(
            [
                f"Relationship: {sender_relationship}",
                f"Requested tone: {tone or 'direct'}",
                f"Extra instruction: {instruction or 'none'}",
                wrap_untrusted("style_notes", style_notes or "No stored style notes."),
                wrapped,
            ]
        )
        payload = await self._gemini.generate_json(
            model=self._model,
            system_prompt=load_prompt("draft_reply"),
            user_prompt=user_prompt,
            schema=DraftSchema,
        )
        return DraftSchema.model_validate(payload)
