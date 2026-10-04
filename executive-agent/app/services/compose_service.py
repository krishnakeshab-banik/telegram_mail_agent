"""Turn an address and a note into a new email. This module never sends mail."""

import re
from dataclasses import dataclass

_ADDRESS = re.compile(r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PREFIX = re.compile(
    r"^(?:please\s+)?(?:write|send|compose|draft)\s+(?:an?\s+)?(?:e-?mail|mail)\s+to\s+"
    r"|^(?:e-?mail|mail|compose)\s+(?:to\s+)?",
    re.IGNORECASE,
)
_FILLER = re.compile(
    r"^(?:please\s+)?(?:asking\s+(?:her|him|them)\s+to\s+|ask\s+(?:her|him|them)\s+to\s+"
    r"|tell(?:ing)?\s+(?:her|him|them)\s+(?:that\s+)?|say(?:ing)?\s+(?:that\s+)?|that\s+"
    r"|about\s+|regarding\s+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ComposeRequest:
    """Recipient and the note the owner wants turned into an email."""

    recipient: str
    message: str


def parse_compose(text: str, *, explicit: bool = False) -> ComposeRequest | None:
    """Read a recipient and note from the owner's own message.

    Args:
        text: Telegram text from the owner.
        explicit: True when the text came from /mail or /compose.

    Returns:
        The request, or None when this is not a new-mail instruction.
        An empty message means the address was given without the note.
    """
    raw = text.strip()
    if not raw:
        return None
    if not explicit and _PREFIX.match(raw) is None:
        return None
    remainder = _PREFIX.sub("", raw, count=1).strip()
    found = _ADDRESS.search(remainder)
    if found is None:
        return None
    note = f"{remainder[: found.start()]} {remainder[found.end() :]}".strip(" ,:;-\n\t")
    note = _FILLER.sub("", note).strip()
    return ComposeRequest(recipient=found.group(0), message=note)


def structure_mail(message: str, *, tone: str) -> tuple[str, str]:
    """Build a subject and body using only the owner's words.

    Args:
        message: What the owner wants said.
        tone: direct, formal, or friendly.

    Returns:
        Subject and body. No facts are added.
    """
    note = " ".join(message.split()).strip()
    if note and note[-1] not in ".!?":
        note = f"{note}."
    if note:
        note = note[0].upper() + note[1:]
    subject = _subject(note)
    greeting = "Hello," if tone == "formal" else "Hi,"
    closing = "Regards," if tone == "formal" else "Thanks,"
    body = f"{greeting}\n\n{note}\n\n{closing}" if note else f"{greeting}\n\n{closing}"
    return subject, body


def _subject(note: str) -> str:
    clause = re.split(r"[.!?]", note, maxsplit=1)[0].strip()
    if len(clause) > 70:
        shortened = clause[:67].rsplit(" ", 1)[0]
        clause = shortened or clause[:70]
    return clause or "Note"
