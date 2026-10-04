"""Google OAuth token load, refresh, and encrypted storage."""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.constants import GOOGLE_SCOPES
from app.db.base import session_scope
from app.db.models.oauth_token import OAuthToken
from app.db.repositories.state_repository import OAuthRepository
from app.exceptions import AuthExpiredError, ConfigurationError
from app.utils.logging import get_logger
from app.utils.security import decrypt_text, encrypt_text
from app.utils.time import utcnow

logger = get_logger(__name__)
_TOKEN_URI = "https://oauth2.googleapis.com/token"
_REFRESH_SKEW = timedelta(seconds=90)


class StaticAccess:
    """Auth stand-in that returns one already issued access token."""

    def __init__(self, access_token: str) -> None:
        """Store the bearer token.

        Args:
            access_token: Token that is still valid.
        """
        self._access_token = access_token

    async def get_access_token(self) -> str:
        """Return the stored bearer token."""
        return self._access_token


class GoogleAuth:
    """Load encrypted tokens, refresh them, and persist the new access token."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], settings: Settings
    ) -> None:
        """Store collaborators.

        Args:
            session_factory: Database session factory.
            settings: Process settings, including the Fernet key.
        """
        self._sessions = session_factory
        self._settings = settings

    async def save_tokens(
        self,
        *,
        access_token: str,
        refresh_token: str,
        expiry: datetime | None,
        account_email: str,
    ) -> None:
        """Encrypt and store Google tokens, replacing any previous row.

        Args:
            access_token: OAuth access token.
            refresh_token: OAuth refresh token.
            expiry: Access-token expiry, if known.
            account_email: Mailbox address the token belongs to.
        """
        encrypted_access = encrypt_text(access_token, self._settings.fernet_key)
        encrypted_refresh = encrypt_text(refresh_token, self._settings.fernet_key)
        async with session_scope(self._sessions) as session:
            repo = OAuthRepository(session)
            existing = await repo.get_google()
            row = existing or OAuthToken(provider="google")
            row.account_email = account_email
            row.encrypted_access_token = encrypted_access
            row.encrypted_refresh_token = encrypted_refresh
            row.expiry = expiry
            row.scopes = " ".join(GOOGLE_SCOPES)
            row.updated_at = utcnow()
            if existing is None:
                await repo.add(row)

    async def get_access_token(self) -> str:
        """Return a valid access token, refreshing it when it is near expiry.

        Returns:
            Bearer token for Gmail and Calendar calls.

        Raises:
            AuthExpiredError: When no token is stored or refresh fails.
        """
        if self._settings.app_mode == "demo":
            return "demo"
        async with session_scope(self._sessions) as session:
            row = await OAuthRepository(session).get_google()
            if row is None or not row.encrypted_refresh_token:
                raise AuthExpiredError("Google is not authorized. Run scripts/authorize_google.py.")
            access = decrypt_text(row.encrypted_access_token, self._settings.fernet_key)
            refresh = decrypt_text(row.encrypted_refresh_token, self._settings.fernet_key)
            expiry = row.expiry
        if access and expiry and expiry - _REFRESH_SKEW > utcnow():
            return access
        refreshed = await asyncio.to_thread(self._refresh, refresh)
        await self.save_tokens(
            access_token=refreshed[0],
            refresh_token=refresh,
            expiry=refreshed[1],
            account_email=await self.account_email(),
        )
        return refreshed[0]

    async def account_email(self) -> str:
        """Return the mailbox stored with the token, or an empty string."""
        async with session_scope(self._sessions) as session:
            row = await OAuthRepository(session).get_google()
            return row.account_email if row else ""

    def refresh(self, refresh_token: str) -> tuple[str, datetime]:
        """Exchange a refresh token for a new access token.

        Args:
            refresh_token: Stored Google refresh token.

        Returns:
            Access token and its expiry.
        """
        return self._refresh(refresh_token)

    def _refresh(self, refresh_token: str) -> tuple[str, datetime]:
        if not self._settings.google_client_id or not self._settings.google_client_secret:
            raise ConfigurationError("Google OAuth client id and secret are required.")
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
        except ImportError as exc:
            raise AuthExpiredError("google-auth is not installed.") from exc
        credentials = Credentials(  # type: ignore[no-untyped-call]
            token=None,
            refresh_token=refresh_token,
            token_uri=_TOKEN_URI,
            client_id=self._settings.google_client_id,
            client_secret=self._settings.google_client_secret,
            scopes=list(GOOGLE_SCOPES),
        )
        try:
            credentials.refresh(Request())  # type: ignore[no-untyped-call]
        except Exception as exc:
            logger.warning("google_refresh_failed", error_type=type(exc).__name__)
            raise AuthExpiredError(
                "Google authorization expired. Run scripts/authorize_google.py."
            ) from exc
        expiry = credentials.expiry or (datetime.now(UTC) + timedelta(hours=1))
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        if not credentials.token:
            raise AuthExpiredError("Google token refresh returned no access token.")
        return credentials.token, expiry
