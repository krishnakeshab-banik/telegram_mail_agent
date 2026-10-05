"""Web signup: state, Google account rules, onboarding, and deletion."""

import asyncio
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

from app.db.base import session_scope
from app.db.models.email import EmailMessage
from app.db.repositories.email_repository import EmailRepository
from app.db.repositories.state_repository import OAuthRepository
from app.db.repositories.user_repository import UserRepository
from app.db.user_context import user_scope
from app.exceptions import ConfigurationError
from app.google.oauth_web import read_state, sign_state
from app.services.container import Container
from app.utils.time import utcnow
from app.web.server import serve_console


class FakeGoogle:
    """In-memory Google token endpoint."""

    def __init__(self, email: str = "person@example.com") -> None:
        self.email = email
        self.revoked: list[str] = []

    async def exchange(self, code: str, verifier: str, redirect: str) -> tuple[str, str, object]:
        del verifier, redirect
        if code == "bad":
            raise ConfigurationError("Google rejected the sign-in.")
        return "access-token", "refresh-token", utcnow()

    async def profile(self, access_token: str) -> str:
        del access_token
        return self.email

    async def revoke(self, token: str) -> None:
        self.revoked.append(token)


def _prepare(agent: Container, google: FakeGoogle) -> None:
    agent.settings.public_base_url = "https://agent.example"
    agent.settings.google_client_id = "client"
    agent.settings.google_client_secret = "secret"
    agent.accounts._google = google


def _state_from(url: str) -> str:
    return parse_qs(urlsplit(url).query)["state"][0]


async def test_reused_and_expired_state_are_rejected(agent: Container) -> None:
    google = FakeGoogle()
    _prepare(agent, google)
    link = await agent.accounts.connect_link(42, 100)
    state = _state_from(link.buttons[0][0].url)
    assert (await agent.accounts.complete("ok", state)).reason == "ok"
    assert (await agent.accounts.complete("ok", state)).reason == "reused"
    expired = sign_state(
        user_id=1,
        nonce="gone",
        expires_at=utcnow() - timedelta(minutes=1),
        key=agent.settings.fernet_key,
    )
    assert read_state(expired, agent.settings.fernet_key, utcnow()) is None
    assert (await agent.accounts.complete("ok", expired)).reason == "expired"


async def test_a_google_account_can_belong_to_only_one_telegram_user(agent: Container) -> None:
    google = FakeGoogle("shared@example.com")
    _prepare(agent, google)
    first = await agent.accounts.connect_link(42, 100)
    assert (
        await agent.accounts.complete("ok", _state_from(first.buttons[0][0].url))
    ).reason == "ok"
    await agent.accounts.agree(77, "ada", 200)
    second = await agent.accounts.connect_link(77, 200)
    result = await agent.accounts.complete("ok", _state_from(second.buttons[0][0].url))
    assert result.reason == "linked"
    async with session_scope(agent.sessions) as session:
        other = await UserRepository(session).get_by_telegram(77)
    assert other is not None
    assert other.google_email == ""


async def test_one_telegram_user_cannot_switch_google_account(agent: Container) -> None:
    google = FakeGoogle("first@example.com")
    _prepare(agent, google)
    link = await agent.accounts.connect_link(42, 100)
    assert (await agent.accounts.complete("ok", _state_from(link.buttons[0][0].url))).reason == "ok"
    google.email = "second@example.com"
    again = await agent.accounts.connect_link(42, 100)
    result = await agent.accounts.complete("ok", _state_from(again.buttons[0][0].url))
    assert result.reason == "linked"


async def test_invite_code_cap_and_onboarding_summary(agent: Container) -> None:
    google = FakeGoogle("new@example.com")
    _prepare(agent, google)
    agent.settings.signup_mode = "invite"
    agent.settings.invite_code = "letmein"
    asked = await agent.accounts.agree(88, "ada", 300)
    assert "invite code" in asked.text
    wrong = await agent.accounts.accept_text(88, "nope")
    assert wrong is not None and "not valid" in wrong.text
    accepted = await agent.accounts.accept_text(88, "letmein")
    assert accepted is not None and accepted.buttons
    done = await agent.accounts.complete("ok", _state_from(accepted.buttons[0][0].url))
    assert done.reason == "ok"
    await agent.accounts.choose(88, "timezone", "Asia/Kolkata")
    await agent.accounts.choose(88, "quiet", "22:00-07:00")
    summary = await agent.accounts.choose(88, "reminders", "360,30")
    assert "last 7 days" in summary.text
    async with session_scope(agent.sessions) as session:
        created = await UserRepository(session).get_by_telegram(88)
    assert created is not None
    assert created.status == "active"
    assert created.timezone == "Asia/Kolkata"

    agent.settings.max_users = 2
    blocked = await agent.accounts.agree(89, "bea", 301)
    assert "full" in blocked.text


async def test_disconnect_revokes_and_deleteme_removes_only_that_account(agent: Container) -> None:
    google = FakeGoogle()
    _prepare(agent, google)
    await agent.accounts._auth.save_tokens(
        access_token="access-token",
        refresh_token="refresh-token",
        expiry=utcnow() + timedelta(hours=1),
        account_email="owner@example.com",
    )
    async with session_scope(agent.sessions) as session:
        owner = await UserRepository(session).get(1)
        assert owner is not None
        owner.google_email = "owner@example.com"
        second = await UserRepository(session).add(
            type(owner)(telegram_user_id=90, status="active", google_email="other@example.com")
        )
        second_id = second.id
        await EmailRepository(session, user_id=1).add(
            EmailMessage(gmail_message_id="owner-mail", thread_id="t", subject="keep")
        )
        await EmailRepository(session, user_id=second_id).add(
            EmailMessage(gmail_message_id="other-mail", thread_id="t2", subject="drop")
        )
    kept = await agent.accounts.disconnect(42, "keep")
    assert "Disconnected" in kept.text
    assert google.revoked == ["refresh-token"]
    async with session_scope(agent.sessions) as session:
        owner = await UserRepository(session).get(1)
        assert owner is not None and owner.status == "disconnected"
        assert owner.google_email == "owner@example.com"
        with user_scope(1):
            assert await OAuthRepository(session).get_google() is None
    removed = await agent.accounts.delete_confirm(90)
    assert "deleted" in removed.text
    async with session_scope(agent.sessions) as session:
        assert await UserRepository(session).get_by_telegram(90) is None
        with user_scope(1):
            kept_mail = await EmailRepository(session).get_by_gmail_id("owner-mail")
        with user_scope(second_id):
            dropped = await EmailRepository(session, user_id=second_id).get_by_gmail_id(
                "other-mail"
            )
    assert kept_mail is not None
    assert dropped is None


async def test_old_message_bodies_are_purged(agent: Container) -> None:
    async with session_scope(agent.sessions) as session:
        await EmailRepository(session).add(
            EmailMessage(
                gmail_message_id="old",
                thread_id="t",
                body_text="secret body",
                received_at=utcnow() - timedelta(days=40),
            )
        )
    assert await agent.accounts.purge_old_bodies() == 1
    async with session_scope(agent.sessions) as session:
        stored = await EmailRepository(session).get_by_gmail_id("old")
    assert stored is not None
    assert stored.body_text == ""


async def test_callback_and_health_return_no_mailbox_data(agent: Container) -> None:
    async def on_oauth(code: str, state: str, error: str) -> bytes:
        assert code == "abc"
        assert state == "xyz"
        assert error == ""
        return b"<p>You can close this page.</p>"

    server = await serve_console(0, on_oauth)
    sockets = server.sockets or []
    port = sockets[0].getsockname()[1]
    try:
        health = await _get(port, "/health")
        callback = await _get(port, "/oauth/google/callback?code=abc&state=xyz")
        home = await _get(port, "/")
        logs = await _get(port, "/api/logs")
    finally:
        server.close()
        await server.wait_closed()
    assert b'"status":"ok"' in health
    assert b"@" not in health
    assert b"You can close this page." in callback
    assert b"not_found" in home
    assert b"not_found" in logs


async def _get(port: int, path: str) -> bytes:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(f"GET {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n".encode())
    await writer.drain()
    data = await reader.read()
    writer.close()
    await writer.wait_closed()
    return data
