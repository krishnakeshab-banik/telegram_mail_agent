"""OTP storage. Codes are encrypted, and alerts never include them."""

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import session_scope
from app.db.models.otp_entry import OtpEntry
from app.db.repositories.email_repository import EmailRepository
from app.db.repositories.folder_repository import FolderRepository
from app.db.user_context import peek_user_id
from app.exceptions import UnscopedQueryError
from app.services.folder_rules import extract_code, looks_like_otp, mask_code
from app.utils.security import decrypt_for_user, encrypt_for_user
from app.utils.time import utcnow

REVEAL_SECONDS = 60


class OtpVault:
    """Store, mask, reveal, and purge one-time codes."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession], fernet_key: str) -> None:
        """Store collaborators.

        Args:
            session_factory: Database session factory.
            fernet_key: Key used to encrypt the code at rest.
        """
        self._sessions = session_factory
        self._key = fernet_key

    async def remember(self, email_id: int, sender: str, text: str) -> str:
        """Store a code if one is present and return the mask.

        Args:
            email_id: Local email id.
            sender: Sender address.
            text: Subject plus body. Treated as untrusted.

        Returns:
            Masked code, or an empty string when no code was found.
        """
        if not looks_like_otp(text, ""):
            return ""
        code = extract_code(text)
        if not code:
            return ""
        masked = mask_code(code)
        async with session_scope(self._sessions) as session:
            repo = FolderRepository(session)
            if await repo.otp_for_email(email_id) is None:
                await repo.add_otp(
                    OtpEntry(
                        email_id=email_id,
                        sender=sender[:320],
                        masked_code=masked,
                        encrypted_code=encrypt_for_user(code, self._key, _required_user_id()),
                    )
                )
        return masked

    async def reveal(self, email_id: int) -> tuple[str, int]:
        """Return the code and how many seconds it should stay on screen.

        Args:
            email_id: Local email id.

        Returns:
            Plain code and the reveal lifetime in seconds.
        """
        async with session_scope(self._sessions) as session:
            entry = await FolderRepository(session).otp_for_email(email_id)
        if entry is None:
            return "", REVEAL_SECONDS
        return decrypt_for_user(entry.encrypted_code, self._key, entry.user_id), REVEAL_SECONDS

    async def purge_expired(self) -> int:
        """Blank OTP email bodies older than 24 hours.

        Returns:
            Number of bodies cleared.
        """
        cutoff = utcnow() - timedelta(hours=24)
        cleared = 0
        async with session_scope(self._sessions) as session:
            emails = EmailRepository(session)
            statement_ids = await FolderRepository(session).messages_for(
                "otps", limit=100, offset=0
            )
            for message in statement_ids:
                if message.received_at <= cutoff and message.body_text:
                    stored = await emails.get(message.id)
                    if stored is not None:
                        stored.body_text = ""
                        cleared += 1
        return cleared


def _required_user_id() -> int:
    user_id = peek_user_id()
    if user_id is None:
        raise UnscopedQueryError("A user id is required to store a code.")
    return user_id
