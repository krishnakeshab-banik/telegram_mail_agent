"""Reply variants and pre-send warnings. Nothing here sends mail."""

import re
from dataclasses import dataclass

from app.ai.prompt_loader import load_prompt

_ATTACHED = re.compile(r"\battached\b", re.IGNORECASE)
_CHIPS = (
    ("Yes, confirmed", "Yes, confirmed."),
    ("Thanks, noted", "Thanks, noted."),
    ("Need more time", "I need a little more time before I can answer."),
)


@dataclass(frozen=True)
class ReplyVariant:
    """One suggested reply the user can preview."""

    label: str
    body: str


@dataclass(frozen=True)
class ReplyPreview:
    """Full preview shown before an explicit Send tap."""

    to: str
    subject: str
    body: str
    warning: str


class ReplySuggestionService:
    """Build reply options from the owner's instruction or three standard tones."""

    def variants(
        self, *, sender_name: str, subject: str, instruction: str = ""
    ) -> list[ReplyVariant]:
        """Return reply choices. An instruction replaces the three defaults.

        Args:
            sender_name: Display name of the recipient.
            subject: Original subject.
            instruction: Owner text such as "reply yes and ask for the invoice".

        Returns:
            One or three variants. None of them are sent.
        """
        if instruction.strip():
            return [ReplyVariant("Instruction", _expand(instruction, sender_name, subject))]
        name = sender_name or "there"
        topic = subject or "your note"
        short, detailed, decline = _style_labels()
        return [
            ReplyVariant(short, f"Thanks {name}, noted on {topic}."),
            ReplyVariant(
                detailed,
                f"Hi {name}, thanks for the note about {topic}. I will follow up with the details shortly.",
            ),
            ReplyVariant(
                decline,
                f"Hi {name}, thanks for thinking of me. I can't take {topic} on right now.",
            ),
        ]

    def chips(self) -> list[ReplyVariant]:
        """Return one-tap replies. Preview still requires Send."""
        return [ReplyVariant(label, body) for label, body in _CHIPS]

    def preview(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        has_attachment: bool,
        cc_count: int = 0,
        known_contact: bool = True,
    ) -> ReplyPreview:
        """Assemble the preview and any safety warning.

        Args:
            to: Recipient address.
            subject: Outgoing subject.
            body: Draft body.
            has_attachment: Whether a file will actually be attached.
            cc_count: How many extra recipients a reply-all would include.
            known_contact: Whether this recipient is already in contacts.

        Returns:
            Preview. Sending still requires a separate approval.
        """
        warnings: list[str] = []
        if _ATTACHED.search(body) and not has_attachment:
            warnings.append("This draft says attached, but there is no attachment.")
        if cc_count >= 5:
            warnings.append("Reply-all would reach many people.")
        if to and not known_contact:
            warnings.append("This recipient is new.")
        return ReplyPreview(to=to, subject=subject, body=body, warning=" ".join(warnings))


def _style_labels() -> tuple[str, str, str]:
    labels = [
        line.split(":", 1)[0].strip()
        for line in load_prompt("reply_variants").splitlines()
        if ":" in line and not line.startswith("#")
    ]
    if len(labels) < 3:
        return ("Short", "Detailed", "Decline")
    return (labels[0], labels[1], labels[2])


def _expand(instruction: str, sender_name: str, subject: str) -> str:
    text = instruction.strip()
    lowered = text.lower()
    name = sender_name or "there"
    if "yes" in lowered and "invoice" in lowered:
        return f"Hi {name}, yes — that works. Could you please share the invoice for {subject}?"
    return f"Hi {name}, {text[0].lower() + text[1:] if text else text}"
