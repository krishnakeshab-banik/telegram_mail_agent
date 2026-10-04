"""Apply Gmail labels only after the owner approves."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.constants import GMAIL_LABEL_PREFIX, ApprovalAction
from app.db.base import session_scope
from app.db.repositories.analysis_repository import AnalysisRepository
from app.db.repositories.email_repository import EmailRepository
from app.exceptions import RecordNotFoundError
from app.google.gmail_client import MailboxClient
from app.services.approval_service import ApprovalService


class LabelService:
    """Create an approval, then attach an Agent/* label after confirmation."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        mailbox: MailboxClient,
        approvals: ApprovalService,
    ) -> None:
        """Store collaborators.

        Args:
            session_factory: Database session factory.
            mailbox: Live or demo Gmail client.
            approvals: Confirmation gate.
        """
        self._sessions = session_factory
        self._mailbox = mailbox
        self._approvals = approvals

    async def request(self, email_id: int, telegram_user_id: int) -> int:
        """Open an approval to label one message.

        Args:
            email_id: Local email id.
            telegram_user_id: Owner who must confirm.

        Returns:
            Approval id.
        """
        async with session_scope(self._sessions) as session:
            message = await EmailRepository(session).get(email_id)
            analysis = await AnalysisRepository(session).get_by_email(email_id)
        if message is None or analysis is None:
            raise RecordNotFoundError("That email has not been classified yet.")
        return await self._approvals.create(
            action=ApprovalAction.APPLY_LABEL,
            payload={"gmail_message_id": message.gmail_message_id, "category": analysis.category},
            summary=f"Apply Agent/{analysis.category} label",
            source_email_id=email_id,
            telegram_user_id=telegram_user_id,
        )

    async def execute(self, payload: dict[str, Any]) -> str:
        """Apply the approved category label.

        Args:
            payload: Includes gmail_message_id and category.

        Returns:
            Short result summary.
        """
        category = str(payload.get("category", "other")).title()
        name = f"{GMAIL_LABEL_PREFIX}/{category}"
        labels = await self._mailbox.list_labels()
        label_id = labels.get(name) or await self._mailbox.create_label(name)
        await self._mailbox.modify_labels(str(payload["gmail_message_id"]), [label_id], [])
        return f"Applied label {name}."
