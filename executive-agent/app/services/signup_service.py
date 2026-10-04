"""Connect a Telegram user to a Google account."""

import asyncio
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.constants import GOOGLE_SCOPES
from app.db.base import session_scope
from app.db.models.member import Member
from app.db.repositories.member_repository import MemberRepository
from app.db.repositories.state_repository import SyncStateRepository
from app.exceptions import ConfigurationError, DemoModeError
from app.google.auth import GoogleAuth, StaticAccess
from app.google.gmail_client import GmailClient
from app.services.sync_service import SyncService
from app.utils.security import decrypt_text, encrypt_text
from app.utils.time import utcnow


class SignupService:
    """Register Telegram users and sync each connected mailbox."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        auth: GoogleAuth,
        sync: SyncService,
    ) -> None:
        """Store collaborators.

        Args:
            session_factory: Database session factory.
            settings: OAuth client settings.
            auth: Primary token store and refresh helper.
            sync: Importer used for additional mailboxes.
        """
        self._sessions = session_factory
        self._settings = settings
        self._auth = auth
        self._sync = sync

    async def is_member(self, telegram_user_id: int) -> bool:
        """Return whether this Telegram user has signed up."""
        async with session_scope(self._sessions) as session:
            row = await MemberRepository(session).get_by_telegram(telegram_user_id)
        return row is not None

    async def connect(self, telegram_user_id: int, chat_id: int) -> str:
        """Open Google consent and store the account for this Telegram user.

        Args:
            telegram_user_id: Person who sent /signup.
            chat_id: Chat that should receive the result.

        Returns:
            Connected mailbox address.
        """
        if self._settings.app_mode == "demo":
            raise DemoModeError("Signup needs APP_MODE=live and Google OAuth credentials.")
        access, refresh, expiry = await asyncio.to_thread(self._browser_consent)
        email = await self._mailbox_email(access)
        await self._store_member(telegram_user_id, chat_id, email, access, refresh, expiry)
        if await self._should_become_primary(telegram_user_id):
            await self._auth.save_tokens(
                access_token=access,
                refresh_token=refresh,
                expiry=expiry,
                account_email=email,
            )
            await self._reset_primary_backfill()
        return email

    async def sync_connected(self) -> int:
        """Pull mail for signed-up accounts other than the primary mailbox.

        Returns:
            Number of newly stored messages.
        """
        if self._settings.app_mode == "demo":
            return 0
        primary = await self._auth.account_email()
        async with session_scope(self._sessions) as session:
            members = await MemberRepository(session).list_linked()
            copies = [
                (
                    item.telegram_user_id,
                    item.encrypted_refresh_token,
                    item.history_id,
                    item.backfill_done,
                    item.account_email,
                )
                for item in members
            ]
        inserted = 0
        for user_id, encrypted_refresh, history_id, done, email in copies:
            if email and email == primary:
                continue
            inserted += await self._sync_one(user_id, encrypted_refresh, history_id, done)
        return inserted

    async def _sync_one(
        self, user_id: int, encrypted_refresh: str, history_id: str, done: bool
    ) -> int:
        refresh = decrypt_text(encrypted_refresh, self._settings.fernet_key)
        access, expiry = await asyncio.to_thread(self._auth.refresh, refresh)
        client = GmailClient(
            StaticAccess(access), requests_per_minute=self._settings.google_requests_per_minute
        )
        try:
            created, new_history, backfill_done = await self._sync.import_account(
                client, history_id=history_id, backfill_done=done
            )
            email, _history = await client.get_profile()
        finally:
            await client.aclose()
        await self._update_cursor(
            user_id, email, access, refresh, expiry, new_history, backfill_done
        )
        return len(created)

    async def _should_become_primary(self, telegram_user_id: int) -> bool:
        if telegram_user_id in self._settings.allowed_user_ids:
            return True
        return not await self._auth.account_email()

    async def _reset_primary_backfill(self) -> None:
        async with session_scope(self._sessions) as session:
            state = await SyncStateRepository(session).get_singleton()
            state.backfill_done = False
            state.history_id = ""
            state.updated_at = utcnow()

    async def _mailbox_email(self, access_token: str) -> str:
        client = GmailClient(
            StaticAccess(access_token),
            requests_per_minute=self._settings.google_requests_per_minute,
        )
        try:
            email, _history = await client.get_profile()
        finally:
            await client.aclose()
        return email

    def _browser_consent(self) -> tuple[str, str, datetime | None]:
        if not self._settings.google_client_id or not self._settings.google_client_secret:
            raise ConfigurationError("Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET first.")
        from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import-untyped]

        flow = InstalledAppFlow.from_client_config(
            {
                "installed": {
                    "client_id": self._settings.google_client_id,
                    "client_secret": self._settings.google_client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://localhost:8080/"],
                }
            },
            list(GOOGLE_SCOPES),
        )
        credentials = flow.run_local_server(port=8080, access_type="offline", prompt="consent")
        if not credentials.refresh_token:
            raise ConfigurationError(
                "Google did not return a refresh token. Remove the app's access and try /signup again."
            )
        expiry = credentials.expiry
        return credentials.token or "", credentials.refresh_token, expiry

    async def _store_member(
        self,
        telegram_user_id: int,
        chat_id: int,
        email: str,
        access: str,
        refresh: str,
        expiry: datetime | None,
    ) -> None:
        async with session_scope(self._sessions) as session:
            repo = MemberRepository(session)
            row = await repo.get_by_telegram(telegram_user_id)
            if row is None:
                row = Member(telegram_user_id=telegram_user_id, created_at=utcnow())
                await repo.add(row)
            self._fill_member(row, chat_id, email, access, refresh, expiry)

    async def _update_cursor(
        self,
        telegram_user_id: int,
        email: str,
        access: str,
        refresh: str,
        expiry: datetime,
        history_id: str,
        backfill_done: bool,
    ) -> None:
        async with session_scope(self._sessions) as session:
            row = await MemberRepository(session).get_by_telegram(telegram_user_id)
            if row is None:
                return
            self._fill_member(row, row.chat_id, email, access, refresh, expiry)
            row.history_id = history_id
            row.backfill_done = backfill_done

    def _fill_member(
        self,
        row: Member,
        chat_id: int,
        email: str,
        access: str,
        refresh: str,
        expiry: datetime | None,
    ) -> None:
        row.chat_id = chat_id
        row.account_email = email
        row.encrypted_access_token = encrypt_text(access, self._settings.fernet_key)
        row.encrypted_refresh_token = encrypt_text(refresh, self._settings.fernet_key)
        row.token_expiry = expiry
