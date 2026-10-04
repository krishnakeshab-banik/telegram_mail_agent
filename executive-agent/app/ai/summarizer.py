"""Thread and attachment summaries."""

from app.ai.gemini_client import GeminiClient
from app.ai.prompt_loader import load_prompt
from app.ai.schemas import AttachmentSummarySchema, FocusSchema, ThreadSummarySchema
from app.utils.security import wrap_untrusted


class Summarizer:
    """Summarize threads, attachments, and briefing facts."""

    def __init__(self, gemini: GeminiClient, *, fast_model: str, smart_model: str) -> None:
        """Store model names.

        Args:
            gemini: Shared Gemini wrapper.
            fast_model: Model used for attachments and focus lines.
            smart_model: Model used for thread summaries.
        """
        self._gemini = gemini
        self._fast_model = fast_model
        self._smart_model = smart_model

    async def summarize_thread(self, blocks: list[str]) -> ThreadSummarySchema:
        """Summarize a thread from oldest to newest.

        Args:
            blocks: Plain-text messages, treated as untrusted.

        Returns:
            Validated thread summary.
        """
        wrapped = "\n".join(
            wrap_untrusted(f"thread_message_{index}", block[:2500])
            for index, block in enumerate(blocks, start=1)
        )
        payload = await self._gemini.generate_json(
            model=self._smart_model,
            system_prompt=load_prompt("summarize_thread"),
            user_prompt=wrapped,
            schema=ThreadSummarySchema,
        )
        return ThreadSummarySchema.model_validate(payload)

    async def summarize_attachment_text(self, filename: str, text: str) -> AttachmentSummarySchema:
        """Summarize extracted attachment text.

        Args:
            filename: Original filename.
            text: Extracted text, treated as untrusted.

        Returns:
            Validated attachment summary.
        """
        user_prompt = "\n".join(
            [
                wrap_untrusted("filename", filename),
                wrap_untrusted("attachment_text", text[:8000]),
            ]
        )
        payload = await self._gemini.generate_json(
            model=self._fast_model,
            system_prompt=load_prompt("summarize_attachment"),
            user_prompt=user_prompt,
            schema=AttachmentSummarySchema,
        )
        return AttachmentSummarySchema.model_validate(payload)

    async def summarize_attachment_media(
        self,
        filename: str,
        media: bytes,
        mime_type: str,
    ) -> AttachmentSummarySchema:
        """Summarize an image or scanned document with the multimodal model.

        Args:
            filename: Original filename.
            media: Raw bytes.
            mime_type: IANA type.

        Returns:
            Validated attachment summary.
        """
        payload = await self._gemini.generate_with_media(
            model=self._fast_model,
            system_prompt=load_prompt("summarize_attachment"),
            user_prompt=wrap_untrusted("filename", filename),
            media=media,
            mime_type=mime_type,
            schema=AttachmentSummarySchema,
        )
        return AttachmentSummarySchema.model_validate(payload)

    async def focus_line(self, facts: str) -> str:
        """Turn briefing facts into one focus sentence.

        Args:
            facts: Plain briefing facts, treated as untrusted.

        Returns:
            Focus sentence, or an empty string when the model is disabled.
        """
        if not self._gemini.enabled:
            return ""
        payload = await self._gemini.generate_json(
            model=self._fast_model,
            system_prompt=load_prompt("briefing_focus"),
            user_prompt=wrap_untrusted("briefing_facts", facts[:4000]),
            schema=FocusSchema,
        )
        return FocusSchema.model_validate(payload).focus_line.strip()
