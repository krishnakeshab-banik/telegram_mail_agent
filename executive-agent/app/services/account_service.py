"""Signup, web OAuth, onboarding, disconnect, and account deletion."""

import hashlib
import hmac
import html
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.constants import CallbackPrefix, callback_data
from app.db.base import session_scope
from app.db.models.oauth_state import OAuthState
from app.db.models.user import User
from app.db.repositories.account_repository import AccountRepository
from app.db.repositories.email_repository import EmailRepository
from app.db.repositories.oauth_state_repository import OAuthStateRepository
from app.db.repositories.state_repository import OAuthRepository
from app.db.repositories.user_repository import UserRepository
from app.db.user_context import user_scope
from app.exceptions import ExecutiveAgentError
from app.google.auth import GoogleAuth
from app.google.oauth_web import (
    GoogleTokenPort,
    GoogleWebClient,
    authorization_url,
    new_nonce,
    new_verifier,
    read_state,
    redirect_uri,
    sign_state,
    state_deadline,
)
from app.services.email_pipeline import EmailPipeline
from app.services.preference_service import PreferenceService
from app.services.sync_service import SyncService
from app.services.user_service import UserService
from app.utils.logging import get_logger
from app.utils.security import decrypt_for_user, encrypt_for_user, hash_user_id
from app.utils.time import parse_clock, utcnow

logger = get_logger(__name__)

_PAGE_OK = "You can close this page. Telegram will confirm the connection."
_PAGE_BAD = (
    "This sign-in link is invalid or has expired. Return to Telegram and tap Connect Google again."
)
_TIMEZONES = ("Asia/Kolkata", "UTC", "America/New_York", "Europe/London")


@dataclass(frozen=True)
class FlowButton:
    """One signup button. Exactly one of callback or url is set."""

    label: str
    callback: str = ""
    url: str = ""


@dataclass(frozen=True)
class FlowReply:
    """Text and buttons a handler can send."""

    text: str
    buttons: tuple[tuple[FlowButton, ...], ...] = ()


@dataclass(frozen=True)
class CallbackResult:
    """Outcome of the browser returning from Google."""

    page: str
    reason: str


Notify = Callable[[int, str, tuple[tuple[FlowButton, ...], ...]], Awaitable[None]]


@dataclass(frozen=True)
class Spent:
    """A state nonce after the single-use check."""

    reason: str
    verifier: str = ""
    chat_id: int | None = None


class AccountService:
    """Turn a Telegram user into an isolated account and connect Google."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        auth: GoogleAuth,
        sync: SyncService,
        pipeline: EmailPipeline,
        preferences: PreferenceService,
        users: UserService,
        google: GoogleTokenPort | None = None,
    ) -> None:
        """Store collaborators."""
        self._sessions = session_factory
        self._settings = settings
        self._auth = auth
        self._sync = sync
        self._pipeline = pipeline
        self._preferences = preferences
        self._users = users
        self._google = google or GoogleWebClient(
            settings.google_client_id, settings.google_client_secret
        )
        self._attempts: dict[int, datetime] = {}
        self._code_attempts: dict[int, datetime] = {}
        self._notify: Notify | None = None

    def bind_notifier(self, notify: Notify) -> None:
        """Attach the function that messages a Telegram chat from the web callback."""
        self._notify = notify

    async def present(self, telegram_user_id: int, chat_id: int | None) -> FlowReply:
        """Return the /start screen for this Telegram user."""
        user = await self._users.by_telegram(telegram_user_id)
        if user is None:
            return _intro()
        if chat_id is not None:
            await self._users.remember_chat(user.id, chat_id)
        if user.status == "banned":
            return FlowReply("")
        if user.status == "active" and user.google_email and user.signup_step in {"", "done"}:
            return _connected(user.google_email)
        if user.signup_step in {"invite", "timezone", "quiet", "offsets"}:
            return await self._resume(user, chat_id)
        return _intro()

    async def privacy_text(self) -> FlowReply:
        """Return the privacy notice."""
        days = self._settings.body_retention_days
        return FlowReply(
            "What I read: Gmail messages, labels, and calendar events you allow.\n"
            "What I store: messages, summaries, deadlines, tasks, folders, and "
            "encrypted Google tokens.\n"
            "How long: one-time-code message bodies are deleted after 24 hours. "
            f"Other message bodies are deleted after {days} days. "
            "Summaries and metadata stay until you delete the account.\n"
            "Your controls: /disconnect revokes Google and stops sync. "
            "/deleteme erases your rows and tokens.",
            ((FlowButton("I agree", callback_data(CallbackPrefix.SIGNUP_AGREE)),),),
        )

    async def agree(self, telegram_user_id: int, username: str, chat_id: int | None) -> FlowReply:
        """Record privacy consent and continue signup."""
        if self._throttled(telegram_user_id):
            return FlowReply("Wait a moment, then try again.")
        self._attempts[telegram_user_id] = utcnow()
        async with session_scope(self._sessions) as session:
            repo = UserRepository(session)
            user = await repo.get_by_telegram(telegram_user_id)
            if user is not None and user.status == "banned":
                return FlowReply("")
            if user is None:
                blocked = await self._block_new(repo)
                if blocked is not None:
                    return blocked
                step = "invite" if self._settings.signup_mode == "invite" else "connect"
                user = await repo.add(
                    User(
                        telegram_user_id=telegram_user_id,
                        telegram_username=username[:64],
                        telegram_chat_id=chat_id,
                        status="pending",
                        signup_step=step,
                        timezone=self._settings.timezone,
                        consented_at=utcnow(),
                    )
                )
            else:
                user.telegram_username = username[:64] or user.telegram_username
                if chat_id is not None:
                    user.telegram_chat_id = chat_id
                if user.consented_at is None:
                    user.consented_at = utcnow()
                if user.signup_step == "" and user.status == "pending":
                    user.signup_step = (
                        "invite" if self._settings.signup_mode == "invite" else "connect"
                    )
            user_id = user.id
            step = user.signup_step
        if step == "invite":
            return FlowReply("Send the invite code to continue.")
        return await self._connect_reply(user_id, chat_id, reconnect=False)

    async def accept_text(self, telegram_user_id: int, text: str) -> FlowReply | None:
        """Consume a signup answer or a delete confirmation, or return None."""
        user = await self._users.by_telegram(telegram_user_id)
        if user is None:
            return None
        if await self._preferences.extra("awaiting_delete") == "1":
            if text.strip() == "DELETE":
                return await self.delete_confirm(telegram_user_id)
            await self._preferences.set_extra("awaiting_delete", "")
            return FlowReply("Account delete cancelled.")
        if user.status != "pending":
            return None
        if user.signup_step == "invite":
            return await self._accept_invite(user.id, telegram_user_id, text.strip())
        if user.signup_step == "timezone":
            return await self._set_timezone(user.id, text.strip())
        if user.signup_step == "quiet":
            return await self._set_quiet(user.id, text.strip())
        if user.signup_step == "connect":
            return FlowReply(
                "Tap Connect Google to continue.", await self._connect_buttons(user.id)
            )
        return None

    async def choose(self, telegram_user_id: int, kind: str, value: str) -> FlowReply:
        """Apply an onboarding button."""
        user = await self._users.by_telegram(telegram_user_id)
        if user is None:
            return _intro()
        if kind == "timezone":
            if value == "custom":
                return FlowReply("Send your timezone, for example Asia/Kolkata.")
            return await self._set_timezone(user.id, value)
        if kind == "quiet":
            if value == "custom":
                return FlowReply("Send quiet hours as 22:00-07:00.")
            return await self._set_quiet(user.id, value)
        if kind == "reminders":
            return await self._set_reminders(user.id, value)
        return FlowReply("Send /start to continue.")

    async def connect_link(self, telegram_user_id: int, chat_id: int | None) -> FlowReply:
        """Issue a fresh Connect Google link."""
        user = await self._users.by_telegram(telegram_user_id)
        if user is None or user.consented_at is None:
            return FlowReply("Agree to the privacy note before connecting Google.")
        if chat_id is not None:
            await self._users.remember_chat(user.id, chat_id)
        reconnect = user.status == "disconnected" or bool(user.google_email)
        return await self._connect_reply(
            user.id, chat_id or user.telegram_chat_id, reconnect=reconnect
        )

    async def complete(self, code: str, state: str) -> CallbackResult:
        """Validate state, store tokens, and tell that Telegram user."""
        parsed = read_state(state, self._settings.fernet_key, utcnow())
        if parsed is None:
            return CallbackResult(_PAGE_BAD, "expired")
        user_id, nonce = parsed
        spent = await self._spend_state(user_id, nonce)
        if spent.reason != "ok":
            return CallbackResult(_PAGE_BAD, spent.reason)
        verifier, chat_id = spent.verifier, spent.chat_id
        try:
            access, refresh, expiry = await self._google.exchange(
                code, verifier, redirect_uri(self._settings.public_base_url)
            )
            email = await self._google.profile(access)
        except ExecutiveAgentError:
            logger.warning("oauth_exchange_failed", user=hash_user_id(user_id))
            await self._tell(
                chat_id, FlowReply("Google did not accept that sign-in. Tap Connect Google again.")
            )
            return CallbackResult(_PAGE_BAD, "failed")
        linked = await self._claim_email(user_id, email)
        if linked is not None:
            await self._tell(chat_id, FlowReply(linked))
            return CallbackResult(_PAGE_BAD, "linked")
        with user_scope(user_id):
            await self._auth.save_tokens(
                access_token=access,
                refresh_token=refresh,
                expiry=expiry,
                account_email=email,
            )
            reply = await self._after_connect(user_id, email)
        await self._tell(chat_id, reply)
        logger.info("google_connected", user=hash_user_id(user_id))
        return CallbackResult(_PAGE_OK, "ok")

    async def web_callback(self, code: str, state: str, error: str) -> bytes:
        """Handle the browser redirect and return a page with no mailbox data."""
        if error or not code or not state:
            return _html(_PAGE_BAD)
        result = await self.complete(code, state)
        return _html(result.page)

    async def disconnect_prompt(self) -> FlowReply:
        """Ask whether to keep stored mail after revoking Google."""
        return FlowReply(
            "This revokes Google access and stops sync.",
            (
                (
                    FlowButton(
                        "Keep my data", callback_data(CallbackPrefix.SIGNUP_DISCONNECT, "keep")
                    ),
                    FlowButton(
                        "Delete my data", callback_data(CallbackPrefix.SIGNUP_DISCONNECT, "delete")
                    ),
                ),
            ),
        )

    async def disconnect(self, telegram_user_id: int, choice: str) -> FlowReply:
        """Revoke Google. Delete rows only when the user asks."""
        user = await self._users.by_telegram(telegram_user_id)
        if user is None:
            return FlowReply("")
        if choice == "delete":
            return await self.delete_prompt()
        await self._revoke(user.id)
        async with session_scope(self._sessions) as session:
            stored = await UserRepository(session).get(user.id)
            if stored is not None:
                stored.status = "disconnected"
                stored.signup_step = "done"
        return FlowReply("Disconnected. Sync is stopped and your data is still here.")

    async def delete_prompt(self) -> FlowReply:
        """Ask the user to type DELETE. A second tap does not erase the account."""
        await self._preferences.set_extra("awaiting_delete", "1")
        return FlowReply(
            "This permanently deletes your mail, tasks, tokens, and account. "
            "Type DELETE to confirm. Any other message cancels."
        )

    async def how_it_works(self) -> FlowReply:
        """Explain the five steps and the safety rules."""
        return FlowReply(
            "1. Connect Google from the button. The link expires in 10 minutes.\n"
            "2. I read new mail and file what matters into folders.\n"
            "3. I remind you before deadlines and meetings.\n"
            "4. I draft replies and new emails for you to read.\n"
            "5. You tap confirm before anything is sent or changed.\n\n"
            "Safety: every send and calendar change waits for your approval. "
            "One-time codes stay in a vault and are not alerted. Your data stays yours."
        )

    async def delete_confirm(self, telegram_user_id: int) -> FlowReply:
        """Revoke Google and erase every row for this Telegram user."""
        user = await self._users.by_telegram(telegram_user_id)
        if user is None:
            return FlowReply("There is no account to delete.")
        await self._revoke(user.id)
        async with session_scope(self._sessions) as session:
            await AccountRepository(session).delete_user(user.id, user.telegram_user_id)
        return FlowReply("Your account and stored data are deleted.")

    async def pause_sync(self) -> None:
        """Stop sync after Google rejects this user's token, and tell only them."""
        from app.db.user_context import peek_user_id

        user_id = peek_user_id()
        if user_id is None:
            return
        async with session_scope(self._sessions) as session:
            user = await UserRepository(session).get(user_id)
            if user is None or user.status != "active":
                return
            user.status = "disconnected"
            chat_id = user.telegram_chat_id
        reply = await self._connect_reply(user_id, chat_id, reconnect=True)
        reply = FlowReply(
            "Google access expired. Sync is paused for your account.",
            reply.buttons,
        )
        fallback = chat_id
        if fallback is None:
            fallback = await self._preferences.chat_id()
        await self._tell(fallback, reply)

    async def purge_old_bodies(self) -> int:
        """Blank message bodies older than the retention window."""
        days = self._settings.body_retention_days
        if days < 1:
            return 0
        cutoff = utcnow() - timedelta(days=days)
        async with session_scope(self._sessions) as session:
            return await EmailRepository(session).blank_bodies_before(cutoff)

    async def _resume(self, user: User, chat_id: int | None) -> FlowReply:
        if user.signup_step == "invite":
            return FlowReply("Send the invite code to continue.")
        if user.signup_step == "timezone":
            return _timezone_prompt()
        if user.signup_step == "quiet":
            return _quiet_prompt()
        if user.signup_step == "offsets":
            return _reminder_prompt()
        return await self._connect_reply(user.id, chat_id, reconnect=False)

    async def _block_new(self, repo: UserRepository) -> FlowReply | None:
        if self._settings.signup_mode == "closed":
            return FlowReply("Signup is closed.")
        if await repo.count() >= self._settings.max_users:
            return FlowReply("Signup is full right now.")
        return None

    async def _accept_invite(self, user_id: int, telegram_user_id: int, code: str) -> FlowReply:
        expected = self._settings.invite_code
        if expected and hmac_equal(code, expected):
            async with session_scope(self._sessions) as session:
                user = await UserRepository(session).get(user_id)
                chat_id = None
                if user is not None:
                    user.signup_step = "connect"
                    chat_id = user.telegram_chat_id
            return await self._connect_reply(user_id, chat_id, reconnect=False)
        if self._code_throttled(telegram_user_id):
            return FlowReply("Wait a moment, then try again.")
        self._code_attempts[telegram_user_id] = utcnow()
        return FlowReply("That invite code is not valid.")

    async def _connect_reply(
        self, user_id: int, chat_id: int | None, *, reconnect: bool
    ) -> FlowReply:
        buttons = await self._connect_buttons(user_id, chat_id)
        if not buttons:
            return FlowReply("Connect Google needs PUBLIC_BASE_URL and a Google web client.")
        label = "Reconnect Google" if reconnect else "Connect Google"
        text = (
            "Tap Reconnect Google. The link expires in 10 minutes."
            if reconnect
            else "Tap Connect Google. The link works once and expires in 10 minutes."
        )
        renamed = tuple(
            tuple(FlowButton(label, url=button.url) if button.url else button for button in row)
            for row in buttons
        )
        return FlowReply(text, renamed)

    async def _connect_buttons(
        self, user_id: int, chat_id: int | None = None
    ) -> tuple[tuple[FlowButton, ...], ...]:
        url = await self._issue_url(user_id, chat_id)
        if not url:
            return ()
        return ((FlowButton("Connect Google", url=url),),)

    async def _issue_url(self, user_id: int, chat_id: int | None) -> str:
        base = self._settings.public_base_url.strip()
        if not base or not self._settings.google_client_id:
            return ""
        verifier = new_verifier()
        nonce = new_nonce()
        expires = state_deadline(self._settings.oauth_state_ttl_seconds)
        with user_scope(user_id):
            encrypted = encrypt_for_user(verifier, self._settings.fernet_key, user_id)
            async with session_scope(self._sessions) as session:
                await OAuthStateRepository(session).add(
                    OAuthState(
                        nonce=nonce,
                        encrypted_verifier=encrypted,
                        telegram_chat_id=chat_id,
                        expires_at=expires,
                    )
                )
        state = sign_state(
            user_id=user_id, nonce=nonce, expires_at=expires, key=self._settings.fernet_key
        )
        return authorization_url(
            client_id=self._settings.google_client_id,
            redirect_uri=redirect_uri(base),
            state=state,
            verifier=verifier,
        )

    async def _spend_state(self, user_id: int, nonce: str) -> Spent:
        with user_scope(user_id):
            async with session_scope(self._sessions) as session:
                row = await OAuthStateRepository(session).get_by_nonce(nonce)
                if row is None or row.used_at is not None:
                    return Spent(reason="reused")
                if row.expires_at <= utcnow():
                    row.used_at = utcnow()
                    return Spent(reason="expired")
                row.used_at = utcnow()
                verifier = decrypt_for_user(
                    row.encrypted_verifier, self._settings.fernet_key, row.user_id
                )
                return Spent(verifier=verifier, chat_id=row.telegram_chat_id, reason="ok")

    async def _claim_email(self, user_id: int, email: str) -> str | None:
        async with session_scope(self._sessions) as session:
            repo = UserRepository(session)
            owner = await repo.find_by_google_email(email)
            if owner is not None and owner.id != user_id:
                return "That Google account is already connected to someone else."
            user = await repo.get(user_id)
            if user is None:
                return "That sign-in does not match an account."
            if user.google_email and user.google_email != email:
                return "This Telegram account is already linked to a different Google account."
            user.google_email = email
            if user.status == "disconnected":
                user.status = "active"
        return None

    async def _after_connect(self, user_id: int, email: str) -> FlowReply:
        async with session_scope(self._sessions) as session:
            user = await UserRepository(session).get(user_id)
            step = "" if user is None else user.signup_step
            status = "" if user is None else user.status
            if user is not None and step in {"", "connect", "invite"} and status == "pending":
                user.signup_step = "timezone"
                step = "timezone"
        if step == "timezone":
            prompt = _timezone_prompt()
            return FlowReply(f"Connected: {email}\n\n{prompt.text}", prompt.buttons)
        return FlowReply(f"Connected: {email}")

    async def _set_timezone(self, user_id: int, name: str) -> FlowReply:
        if not _valid_zone(name):
            return FlowReply("Send a timezone name such as Asia/Kolkata.")
        async with session_scope(self._sessions) as session:
            user = await UserRepository(session).get(user_id)
            if user is not None:
                user.timezone = name
                user.signup_step = "quiet"
        with user_scope(user_id):
            await self._preferences.apply_command(f"timezone {name}")
        return _quiet_prompt()

    async def _set_quiet(self, user_id: int, window: str) -> FlowReply:
        if "-" not in window:
            return FlowReply("Send quiet hours as 22:00-07:00.")
        start, end = (part.strip() for part in window.split("-", 1))
        if parse_clock(start) is None or parse_clock(end) is None:
            return FlowReply("Send quiet hours as 22:00-07:00.")
        async with session_scope(self._sessions) as session:
            user = await UserRepository(session).get(user_id)
            if user is not None:
                user.quiet_start = start
                user.quiet_end = end
                user.signup_step = "offsets"
        with user_scope(user_id):
            await self._preferences.apply_command(f"quiet {start}-{end}")
        return _reminder_prompt()

    async def _set_reminders(self, user_id: int, raw: str) -> FlowReply:
        leads = _parse_offsets(raw)
        if not leads:
            return FlowReply("Choose a reminder option.")
        async with session_scope(self._sessions) as session:
            user = await UserRepository(session).get(user_id)
            threshold = 60
            if user is not None:
                user.reminder_offsets = ",".join(str(item) for item in leads)
                user.signup_step = "done"
                user.status = "active"
                threshold = user.importance_threshold
        with user_scope(user_id):
            await self._preferences.set_reminder_leads(leads)
            return await self._backfill_summary(threshold)

    async def _backfill_summary(self, threshold: int) -> FlowReply:
        try:
            inserted = await self._sync.sync_inbox()
            await self._pipeline.process_pending()
        except ExecutiveAgentError as exc:
            return FlowReply(f"Setup is saved. The first sync did not finish: {exc}")
        async with session_scope(self._sessions) as session:
            important = await EmailRepository(session).count_important(threshold)
        return FlowReply(
            f"Setup is done. Found {len(inserted)} emails in the last 7 days, "
            f"{important} important."
        )

    async def _revoke(self, user_id: int) -> None:
        refresh = ""
        with user_scope(user_id):
            async with session_scope(self._sessions) as session:
                row = await OAuthRepository(session).get_google()
                if row is not None and row.encrypted_refresh_token:
                    try:
                        refresh = decrypt_for_user(
                            row.encrypted_refresh_token, self._settings.fernet_key, row.user_id
                        )
                    except ExecutiveAgentError:
                        refresh = ""
                if row is not None:
                    await session.delete(row)
        if refresh:
            await self._google.revoke(refresh)

    def _throttled(self, telegram_user_id: int) -> bool:
        return self._within(self._attempts, telegram_user_id)

    def _code_throttled(self, telegram_user_id: int) -> bool:
        return self._within(self._code_attempts, telegram_user_id)

    def _within(self, store: dict[int, datetime], telegram_user_id: int) -> bool:
        previous = store.get(telegram_user_id)
        if previous is None:
            return False
        return utcnow() - previous < timedelta(seconds=self._settings.signup_throttle_seconds)

    async def _tell(self, chat_id: int | None, reply: FlowReply) -> None:
        notify = self._notify
        if chat_id is None or notify is None or not reply.text:
            return
        await notify(chat_id, reply.text, reply.buttons)


def hmac_equal(left: str, right: str) -> bool:
    """Compare two codes without short-circuiting on the first difference."""
    actual = hashlib.sha256(left.encode("utf-8")).digest()
    expected = hashlib.sha256(right.encode("utf-8")).digest()
    return hmac.compare_digest(actual, expected)


def _intro() -> FlowReply:
    return FlowReply(
        "👋 Hi, I'm Jarvis, your personal executive assistant.\n\n"
        "I watch your Gmail, flag what matters, keep your deadlines and meetings in order, "
        "and draft replies for you. Nothing is sent or changed until you tap confirm.\n\n"
        "To begin, agree to the privacy note and connect your Google account.",
        (
            (
                FlowButton("Privacy note", callback_data(CallbackPrefix.SIGNUP_PRIVACY)),
                FlowButton("Connect Google", callback_data(CallbackPrefix.SIGNUP_GOOGLE)),
                FlowButton("How it works", callback_data(CallbackPrefix.HOW)),
            ),
        ),
    )


def _connected(email: str) -> FlowReply:
    return FlowReply(
        "👋 Welcome back. Connected to "
        + email
        + ".\n\n"
        "What I do for you:\n"
        "- Alert you to important mail, not noise\n"
        "- Remind you 6 hours before deadlines and 30 minutes before meetings\n"
        "- Schedule meetings and invite people by email\n"
        "- Draft replies and new emails for your approval\n"
        "- Keep jobs, hackathons, bills and more in smart folders\n"
        "- Keep codes and suspicious mail out of your way\n\n"
        "Pick something to start.",
        (
            (
                FlowButton("📅 Today", callback_data(CallbackPrefix.NAV, "today")),
                FlowButton("📥 Important", callback_data(CallbackPrefix.NAV, "important")),
            ),
            (
                FlowButton("🗂 Folders", callback_data(CallbackPrefix.NAV, "folders")),
                FlowButton("➕ Schedule meet", callback_data(CallbackPrefix.NAV, "meet")),
            ),
            (
                FlowButton("⚙️ Settings", callback_data(CallbackPrefix.NAV, "settings")),
                FlowButton("❓ Help", callback_data(CallbackPrefix.NAV, "help")),
            ),
        ),
    )


def _timezone_prompt() -> FlowReply:
    row = tuple(
        FlowButton(name, callback_data(CallbackPrefix.SIGNUP_TIMEZONE, name)) for name in _TIMEZONES
    )
    custom = (FlowButton("I'll type it", callback_data(CallbackPrefix.SIGNUP_TIMEZONE, "custom")),)
    return FlowReply("What timezone should I use?", (row[:2], row[2:], custom))


def _quiet_prompt() -> FlowReply:
    return FlowReply(
        "Quiet hours hold ordinary mail alerts. Critical alerts still arrive.",
        (
            (
                FlowButton(
                    "22:00–07:00", callback_data(CallbackPrefix.SIGNUP_QUIET, "22:00-07:00")
                ),
                FlowButton(
                    "23:00–08:00", callback_data(CallbackPrefix.SIGNUP_QUIET, "23:00-08:00")
                ),
            ),
            (FlowButton("I'll type it", callback_data(CallbackPrefix.SIGNUP_QUIET, "custom")),),
        ),
    )


def _reminder_prompt() -> FlowReply:
    return FlowReply(
        "When should I remind you?",
        (
            (
                FlowButton(
                    "6h before deadlines, 30m before meetings",
                    callback_data(CallbackPrefix.SIGNUP_REMINDERS, "360,30"),
                ),
            ),
            (
                FlowButton(
                    "Also 24h before",
                    callback_data(CallbackPrefix.SIGNUP_REMINDERS, "1440,360,30"),
                ),
            ),
        ),
    )


def _valid_zone(name: str) -> bool:
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return False
    return bool(name)


def _parse_offsets(raw: str) -> tuple[int, ...] | None:
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if not parts or not all(part.isdigit() for part in parts):
        return None
    leads = tuple(sorted({int(part) for part in parts if int(part) > 0}, reverse=True))
    return leads or None


def _html(text: str) -> bytes:
    body = (
        "<!doctype html><meta charset=utf-8><title>Google sign-in</title>"
        f"<p>{html.escape(text)}</p>"
    )
    return body.encode("utf-8")
