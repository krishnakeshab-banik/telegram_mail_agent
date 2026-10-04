"""RFC822 replies sent through the Gmail API."""

import base64
from email.message import EmailMessage as MimeMessage


def build_new_raw(*, recipient: str, subject: str, body: str, signature: str) -> str:
    """Build a base64url RFC822 message that starts a new thread.

    Args:
        recipient: To address.
        subject: Subject line.
        body: Approved plain-text body.
        signature: Optional signature appended by the application.

    Returns:
        Gmail raw payload.
    """
    mime = MimeMessage()
    mime["To"] = recipient
    mime["Subject"] = subject or "Note"
    full_body = body if not signature else f"{body.rstrip()}\n\n{signature}"
    mime.set_content(full_body)
    return base64.urlsafe_b64encode(mime.as_bytes()).decode("utf-8")


def build_reply_raw(
    *,
    recipient: str,
    subject: str,
    body: str,
    in_reply_to: str,
    references: str,
    signature: str,
) -> str:
    """Build a base64url RFC822 reply with threading headers.

    Args:
        recipient: To address.
        subject: Original subject.
        body: Approved plain-text body.
        in_reply_to: Original Message-ID.
        references: Original References header.
        signature: Optional signature appended by the application.

    Returns:
        Gmail raw payload.
    """
    mime = MimeMessage()
    mime["To"] = recipient
    mime["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    if in_reply_to:
        mime["In-Reply-To"] = in_reply_to
        mime["References"] = f"{references} {in_reply_to}".strip()
    full_body = body if not signature else f"{body.rstrip()}\n\n{signature}"
    mime.set_content(full_body)
    return base64.urlsafe_b64encode(mime.as_bytes()).decode("utf-8")
