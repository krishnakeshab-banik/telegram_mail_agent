"""Parse Gmail API message resources into plain text and attachment metadata."""

import base64
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parseaddr, parsedate_to_datetime

from bs4 import BeautifulSoup

from app.constants import EmailDirection
from app.utils.text import collapse_whitespace
from app.utils.time import utcnow

_LINK = re.compile(r"https://(?:meet\.google\.com|[\w.-]*zoom\.us|teams\.microsoft\.com)/\S+")


def find_meeting_links(text: str) -> list[str]:
    """Return up to three video-meeting links found in text.

    Args:
        text: Plain text that may contain meeting URLs.

    Returns:
        Unique links in encounter order.
    """
    found: list[str] = []
    for match in _LINK.findall(text):
        if match not in found:
            found.append(match)
    return found[:3]


@dataclass(frozen=True)
class AttachmentMeta:
    """Metadata for one attachment. Bytes are downloaded later on demand."""

    filename: str
    mime_type: str
    size_bytes: int
    gmail_attachment_id: str


@dataclass(frozen=True)
class ParsedEmail:
    """Normalized Gmail message used by the sync and pipeline layers."""

    gmail_message_id: str
    thread_id: str
    history_id: str
    sender_email: str
    sender_name: str
    to_recipients: str
    cc_recipients: str
    subject: str
    snippet: str
    body_text: str
    labels: list[str]
    received_at: datetime
    is_unread: bool
    is_bulk: bool
    bulk_reason: str
    has_attachments: bool
    in_reply_to: str
    references_header: str
    message_id_header: str
    direction: str
    attachments: list[AttachmentMeta] = field(default_factory=list)
    meeting_links: list[str] = field(default_factory=list)


def parse_gmail_message(resource: dict[str, object]) -> ParsedEmail:
    """Parse a Gmail users.messages resource.

    Args:
        resource: JSON object returned by the Gmail API.

    Returns:
        Normalized message. HTML is converted to text and scripts are dropped.
    """
    payload = resource.get("payload")
    payload_dict = payload if isinstance(payload, dict) else {}
    headers = _headers(payload_dict.get("headers"))
    raw_labels = resource.get("labelIds", [])
    label_items = raw_labels if isinstance(raw_labels, list) else []
    labels = [str(label) for label in label_items if isinstance(label, str)]
    sender_name, sender_email = parseaddr(headers.get("from", ""))
    plain, html, attachments = _walk(payload_dict)
    body = collapse_whitespace(plain or html_to_text(html) or str(resource.get("snippet", "")))
    reason = bulk_reason(headers, labels, sender_email)
    received = _received_at(resource, headers)
    direction = EmailDirection.OUTBOUND if "SENT" in labels else EmailDirection.INBOUND
    return ParsedEmail(
        gmail_message_id=str(resource.get("id", "")),
        thread_id=str(resource.get("threadId", "")),
        history_id=str(resource.get("historyId", "")),
        sender_email=sender_email.lower(),
        sender_name=sender_name,
        to_recipients=headers.get("to", ""),
        cc_recipients=headers.get("cc", ""),
        subject=headers.get("subject", ""),
        snippet=str(resource.get("snippet", "")),
        body_text=body,
        labels=labels,
        received_at=received,
        is_unread="UNREAD" in labels,
        is_bulk=bool(reason),
        bulk_reason=reason,
        has_attachments=bool(attachments),
        in_reply_to=headers.get("in-reply-to", ""),
        references_header=headers.get("references", ""),
        message_id_header=headers.get("message-id", ""),
        direction=direction,
        attachments=attachments,
        meeting_links=find_meeting_links(body),
    )


def html_to_text(value: str) -> str:
    """Convert HTML to text after removing script and style tags.

    Args:
        value: HTML body.

    Returns:
        Plain text.
    """
    soup = BeautifulSoup(value, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return collapse_whitespace(soup.get_text("\n"))


def bulk_reason(headers: dict[str, str], labels: list[str], sender_email: str) -> str:
    """Return why a message looks like bulk mail, or an empty string.

    Args:
        headers: Lowercase header map.
        labels: Gmail label ids.
        sender_email: Sender address.

    Returns:
        A short reason code, or empty when the message should go to the model.
    """
    if "list-unsubscribe" in headers:
        return "list-unsubscribe"
    if headers.get("precedence", "").lower() in {"bulk", "list", "junk"}:
        return "precedence"
    if "CATEGORY_PROMOTIONS" in labels or "CATEGORY_SOCIAL" in labels:
        return "gmail-category"
    local = sender_email.split("@", 1)[0]
    if local.startswith(("no-reply", "noreply", "newsletter", "notifications")):
        return "noreply-sender"
    return ""


def _headers(raw: object) -> dict[str, str]:
    if not isinstance(raw, list):
        return {}
    parsed: dict[str, str] = {}
    for item in raw:
        if isinstance(item, dict):
            parsed[str(item.get("name", "")).lower()] = str(item.get("value", ""))
    return parsed


def _walk(part: dict[str, object]) -> tuple[str, str, list[AttachmentMeta]]:
    mime = str(part.get("mimeType", ""))
    body = part.get("body") if isinstance(part.get("body"), dict) else {}
    attachments: list[AttachmentMeta] = []
    filename = str(part.get("filename", ""))
    attachment_id = str(body.get("attachmentId", "")) if isinstance(body, dict) else ""
    if filename and attachment_id:
        size = int(body.get("size", 0)) if isinstance(body, dict) else 0
        attachments.append(AttachmentMeta(filename, mime, size, attachment_id))
    data = str(body.get("data", "")) if isinstance(body, dict) else ""
    plain = _decode(data) if mime == "text/plain" and data else ""
    html = _decode(data) if mime == "text/html" and data else ""
    raw_parts = part.get("parts", [])
    children = raw_parts if isinstance(raw_parts, list) else []
    for child in children:
        if isinstance(child, dict):
            child_plain, child_html, child_attachments = _walk(child)
            plain = plain or child_plain
            html = html or child_html
            attachments.extend(child_attachments)
    return plain, html, attachments


def _decode(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8", errors="replace")
    except (ValueError, UnicodeError):
        return ""


def _received_at(resource: dict[str, object], headers: dict[str, str]) -> datetime:
    internal = str(resource.get("internalDate", ""))
    if internal.isdigit():
        return datetime.fromtimestamp(int(internal) / 1000, tz=UTC)
    try:
        parsed = parsedate_to_datetime(headers.get("date", ""))
    except (TypeError, ValueError, IndexError):
        return utcnow()
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
