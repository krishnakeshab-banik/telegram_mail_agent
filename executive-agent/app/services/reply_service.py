"""Draft, edit, and send replies. Sending happens only from an approved payload."""

from dataclasses import dataclass
from email.utils import parseaddr
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.drafter import ReplyDrafter
from app.constants import ApprovalAction, EmailDirection, PendingKind
from app.db.base import session_scope
from app.db.models.draft import DraftReply
from app.db.models.email import EmailMessage
from app.db.models.pending_interaction import PendingInteraction
from app.db.repositories.email_repository import EmailRepository
from app.db.repositories.state_repository import DraftRepository, PendingInteractionRepository
from app.exceptions import RecordNotFoundError
from app.google.gmail_client import MailboxClient
from app.services.approval_service import ApprovalService
from app.services.contact_service import ContactService
from app.services.followup_service import FollowUpService
from app.services.mime_message import build_new_raw, build_reply_raw
from app.services.preference_service import PreferenceService
from app.utils.time import utcnow

_EDIT_TTL_MINUTES = 30


@dataclass(frozen=True)
class DraftPreview:
    """Facts needed to render a reply preview."""

    approval_id: int
    draft_id: int
    body: str
    tone: str
    subject: str
    recipient: str


class ReplyService:
    """Generate previews and send mail after the approval gate says yes."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        mailbox: MailboxClient,
        drafter: ReplyDrafter,
        approvals: ApprovalService,
        preferences: PreferenceService,
        contacts: ContactService,
        followups: FollowUpService,
    ) -> None:
        """Store collaborators.

        Args:
            session_factory: Database session factory.
            mailbox: Gmail client used only by the approved send executor.
            drafter: Reply model.
            approvals: Confirmation gate.
            preferences: Tone, signature, and style notes.
            contacts: Relationship context and learning signals.
            followups: Closed when a reply is sent.
        """
        self._sessions = session_factory
        self._mailbox = mailbox
        self._drafter = drafter
        self._approvals = approvals
        self._preferences = preferences
        self._contacts = contacts
        self._followups = followups

    async def create_preview(
        self,
        email_id: int,
        telegram_user_id: int,
        *,
        tone: str = "",
        instruction: str = "",
    ) -> DraftPreview:
        """Draft a reply and open a send approval. Nothing is sent."""
        message, blocks = await self._thread(email_id)
        prefs = await self._preferences.get()
        contact = await self._contacts.get(message.sender_email)
        relationship = contact.relationship_type if contact else "unknown"
        drafted = await self._drafter.draft(
            thread_blocks=blocks,
            sender_relationship=relationship,
            style_notes=prefs.writing_style,
            tone=tone or prefs.tone,
            instruction=instruction,
        )
        approval_id = await self._approvals.create(
            action=ApprovalAction.SEND_EMAIL,
            payload={"email_id": email_id, "body": drafted.body, "tone": drafted.tone_used},
            summary=f"Send reply to {message.sender_email}"[:300],
            source_email_id=email_id,
            telegram_user_id=telegram_user_id,
        )
        async with session_scope(self._sessions) as session:
            draft = await DraftRepository(session).add(
                DraftReply(
                    email_id=email_id,
                    approval_id=approval_id,
                    body=drafted.body,
                    tone=drafted.tone_used,
                    instruction=instruction,
                    original_body=drafted.body,
                    status="preview",
                )
            )
            draft_id = draft.id
        await self._contacts.note_acted(message.sender_email)
        return DraftPreview(
            approval_id=approval_id,
            draft_id=draft_id,
            body=drafted.body,
            tone=drafted.tone_used,
            subject=message.subject,
            recipient=message.sender_email,
        )

    async def stage_body(self, email_id: int, telegram_user_id: int, body: str) -> DraftPreview:
        """Open a send approval for text the owner already chose. Nothing is sent."""
        message, _blocks = await self._thread(email_id)
        approval_id = await self._approvals.create(
            action=ApprovalAction.SEND_EMAIL,
            payload={"email_id": email_id, "body": body, "tone": "suggested"},
            summary=f"Send reply to {message.sender_email}"[:300],
            source_email_id=email_id,
            telegram_user_id=telegram_user_id,
        )
        async with session_scope(self._sessions) as session:
            draft = await DraftRepository(session).add(
                DraftReply(
                    email_id=email_id,
                    approval_id=approval_id,
                    body=body,
                    tone="suggested",
                    instruction="suggestion",
                    original_body=body,
                    status="preview",
                )
            )
            draft_id = draft.id
        return DraftPreview(
            approval_id=approval_id,
            draft_id=draft_id,
            body=body,
            tone="suggested",
            subject=message.subject,
            recipient=message.sender_email,
        )

    async def stage_compose(
        self,
        *,
        recipient: str,
        subject: str,
        body: str,
        instruction: str,
        tone: str,
        telegram_user_id: int,
    ) -> DraftPreview:
        """Open a send approval for a new email. Nothing is sent."""
        payload = {
            "kind": "compose",
            "to": recipient,
            "subject": subject,
            "body": body,
            "tone": tone or "direct",
            "instruction": instruction,
            "original_body": body,
        }
        approval_id = await self._approvals.create(
            action=ApprovalAction.SEND_EMAIL,
            payload=payload,
            summary=f"Send new mail to {recipient}"[:300],
            source_email_id=None,
            telegram_user_id=telegram_user_id,
        )
        return DraftPreview(
            approval_id=approval_id,
            draft_id=0,
            body=body,
            tone=tone or "direct",
            subject=subject,
            recipient=recipient,
        )

    async def begin_edit(self, approval_id: int, telegram_user_id: int) -> None:
        """Ask the next owner message to replace the draft body."""
        from datetime import timedelta

        async with session_scope(self._sessions) as session:
            repo = PendingInteractionRepository(session)
            existing = await repo.get_for_user(telegram_user_id)
            if existing is not None:
                await repo.delete(existing)
            await repo.add(
                PendingInteraction(
                    telegram_user_id=telegram_user_id,
                    kind=PendingKind.EDIT_DRAFT,
                    target_id=approval_id,
                    expires_at=utcnow() + timedelta(minutes=_EDIT_TTL_MINUTES),
                )
            )

    async def apply_pending_edit(self, telegram_user_id: int, text: str) -> DraftPreview | None:
        """Replace a draft when the owner is in edit mode.

        Returns:
            The updated preview, or None when no edit is pending.
        """
        async with session_scope(self._sessions) as session:
            pending = await PendingInteractionRepository(session).get_for_user(telegram_user_id)
            if pending is None or pending.kind != PendingKind.EDIT_DRAFT:
                return None
            if pending.expires_at <= utcnow():
                await PendingInteractionRepository(session).delete(pending)
                return None
            approval_id = pending.target_id
            await PendingInteractionRepository(session).delete(pending)
        return await self._replace_body(approval_id, text, edited=True)

    async def revise(
        self, approval_id: int, *, tone: str = "", instruction: str = ""
    ) -> DraftPreview:
        """Regenerate a preview. The previous approval is cancelled first."""
        payload = await self._approvals.payload(approval_id)
        await self._approvals.reject(approval_id)
        if payload.get("kind") == "compose":
            from app.services.compose_service import structure_mail

            note = str(payload.get("instruction") or payload.get("body") or "")
            if instruction == "shorter":
                note = note.split(".", maxsplit=1)[0]
            subject, body = structure_mail(note, tone=tone or str(payload.get("tone", "direct")))
            return await self.stage_compose(
                recipient=str(payload.get("to", "")),
                subject=subject,
                body=body,
                instruction=note,
                tone=tone or str(payload.get("tone", "direct")),
                telegram_user_id=0,
            )
        return await self.create_preview(
            int(payload["email_id"]),
            0,
            tone=tone or str(payload.get("tone", "")),
            instruction=instruction,
        )

    async def execute_send(self, payload: dict[str, Any]) -> str:
        """Send an approved reply, or a new message when the payload says compose."""
        if payload.get("kind") == "compose":
            return await self._send_composed(payload)
        email_id = int(payload["email_id"])
        body = str(payload["body"])
        message, _blocks = await self._thread(email_id)
        prefs = await self._preferences.get()
        raw = build_reply_raw(
            recipient=message.sender_email,
            subject=message.subject,
            body=body,
            in_reply_to=message.message_id_header,
            references=message.references_header,
            signature=prefs.signature,
        )
        sent_id = await self._mailbox.send_raw(raw, message.thread_id)
        await self._record_sent(message, body, sent_id)
        await self._followups.complete_for_email(email_id)
        original = await self._original_body(email_id)
        if original and original != body:
            await self._preferences.learn_style(original, body)
        return f"Sent reply {sent_id}."

    async def _send_composed(self, payload: dict[str, Any]) -> str:
        recipient = str(payload.get("to", "")).strip()
        subject = str(payload.get("subject", "")).strip() or "Note"
        body = str(payload.get("body", "")).strip()
        if not recipient or not body:
            return "That draft is missing an address or a message. Nothing was sent."
        prefs = await self._preferences.get()
        raw = build_new_raw(
            recipient=recipient, subject=subject, body=body, signature=prefs.signature
        )
        sent_id = await self._mailbox.send_raw(raw, "")
        await self._record_composed(recipient, subject, body, sent_id)
        original = str(payload.get("original_body", ""))
        if original and original != body:
            await self._preferences.learn_style(original, body)
        return f"Sent mail {sent_id}."

    async def _record_composed(self, recipient: str, subject: str, body: str, sent_id: str) -> None:
        async with session_scope(self._sessions) as session:
            emails = EmailRepository(session)
            if await emails.get_by_gmail_id(sent_id) is not None:
                return
            await emails.add(
                EmailMessage(
                    gmail_message_id=sent_id,
                    thread_id=sent_id,
                    sender_email="me",
                    sender_name="me",
                    to_recipients=recipient,
                    subject=subject,
                    body_text=body,
                    received_at=utcnow(),
                    is_unread=False,
                    direction=EmailDirection.OUTBOUND,
                    processed_at=utcnow(),
                    notification_status="skipped",
                )
            )

    async def _replace_body(self, approval_id: int, body: str, *, edited: bool) -> DraftPreview:
        payload = await self._approvals.payload(approval_id)
        payload["body"] = body
        await self._approvals.reject(approval_id)
        if payload.get("kind") == "compose":
            new_id = await self._approvals.create(
                action=ApprovalAction.SEND_EMAIL,
                payload=payload,
                summary=f"Send new mail to {payload.get('to', '')}"[:300],
                source_email_id=None,
                telegram_user_id=None,
            )
            return DraftPreview(
                approval_id=new_id,
                draft_id=0,
                body=body,
                tone=str(payload.get("tone", "direct")),
                subject=str(payload.get("subject", "Note")),
                recipient=str(payload.get("to", "")),
            )
        message, _blocks = await self._thread(int(payload["email_id"]))
        new_id = await self._approvals.create(
            action=ApprovalAction.SEND_EMAIL,
            payload=payload,
            summary=f"Send reply to {message.sender_email}"[:300],
            source_email_id=message.id,
            telegram_user_id=None,
        )
        async with session_scope(self._sessions) as session:
            draft = await DraftRepository(session).get_by_approval(approval_id)
            original = draft.original_body if draft else body
            created = await DraftRepository(session).add(
                DraftReply(
                    email_id=message.id,
                    approval_id=new_id,
                    body=body,
                    tone=str(payload.get("tone", "direct")),
                    was_edited=edited,
                    original_body=original,
                    status="preview",
                )
            )
            draft_id = created.id
        return DraftPreview(
            new_id,
            draft_id,
            body,
            str(payload.get("tone", "direct")),
            message.subject,
            message.sender_email,
        )

    async def _thread(self, email_id: int) -> tuple[EmailMessage, list[str]]:
        async with session_scope(self._sessions) as session:
            message = await EmailRepository(session).get(email_id)
            if message is None:
                raise RecordNotFoundError("That email is not in the local mailbox.")
            thread = await EmailRepository(session).list_thread(message.thread_id)
        if not thread:
            thread = [message]
        blocks = [
            f"From: {item.sender_name} <{item.sender_email}>\nSubject: {item.subject}\n{item.body_text}"
            for item in thread
        ]
        if not any(item.id == message.id for item in thread):
            blocks.append(
                f"From: {message.sender_name}\nSubject: {message.subject}\n{message.body_text}"
            )
        return message, blocks

    async def _record_sent(self, source: EmailMessage, body: str, sent_id: str) -> None:
        async with session_scope(self._sessions) as session:
            emails = EmailRepository(session)
            if await emails.get_by_gmail_id(sent_id) is not None:
                return
            await emails.add(
                EmailMessage(
                    gmail_message_id=sent_id,
                    thread_id=source.thread_id,
                    sender_email=parseaddr(source.to_recipients)[1],
                    sender_name="me",
                    to_recipients=source.sender_email,
                    subject=source.subject,
                    body_text=body,
                    received_at=utcnow(),
                    is_unread=False,
                    direction=EmailDirection.OUTBOUND,
                    processed_at=utcnow(),
                    in_reply_to=source.message_id_header,
                )
            )

    async def _original_body(self, email_id: int) -> str:
        async with session_scope(self._sessions) as session:
            draft = await DraftRepository(session).latest_for_email(email_id)
        return draft.original_body if draft else ""
