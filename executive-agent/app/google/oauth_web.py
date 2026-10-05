"""PKCE, signed OAuth state, and the Google token exchange for the web callback."""

import hashlib
import hmac
import json
import secrets
from base64 import urlsafe_b64decode as _b64decode
from base64 import urlsafe_b64encode
from datetime import datetime, timedelta
from typing import Protocol
from urllib.parse import urlencode

import httpx

from app.constants import GOOGLE_SCOPES
from app.exceptions import ConfigurationError
from app.utils.time import utcnow

_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
_PROFILE_URL = "https://gmail.googleapis.com/gmail/v1/users/me/profile"


def new_verifier() -> str:
    """Return a PKCE code verifier."""
    return secrets.token_urlsafe(64)


def code_challenge(verifier: str) -> str:
    """Return the S256 challenge for a verifier."""
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def new_nonce() -> str:
    """Return a single-use state nonce."""
    return secrets.token_urlsafe(18)


def sign_state(*, user_id: int, nonce: str, expires_at: datetime, key: str) -> str:
    """Sign a state token bound to one user and one nonce."""
    payload = {"u": user_id, "n": nonce, "e": int(expires_at.timestamp())}
    body = urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    encoded = body.decode("utf-8").rstrip("=")
    signature = hmac.new(key.encode("utf-8"), encoded.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def read_state(token: str, key: str, now: datetime) -> tuple[int, str] | None:
    """Return the user id and nonce, or None when the token is bad or expired."""
    encoded, separator, signature = token.partition(".")
    if not encoded or not separator or not signature:
        return None
    expected = hmac.new(key.encode("utf-8"), encoded.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return None
    padded = encoded + "=" * (-len(encoded) % 4)
    try:
        payload = json.loads(_b64decode(padded.encode("utf-8")))
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    user_id = payload.get("u")
    nonce = payload.get("n")
    expires = payload.get("e")
    if not isinstance(user_id, int) or not isinstance(nonce, str) or not isinstance(expires, int):
        return None
    if expires < int(now.timestamp()):
        return None
    return user_id, nonce


def authorization_url(
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    verifier: str,
) -> str:
    """Build the Google consent URL."""
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(GOOGLE_SCOPES),
            "state": state,
            "code_challenge": code_challenge(verifier),
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "false",
        }
    )
    return f"{_AUTH_URL}?{query}"


def redirect_uri(public_base_url: str) -> str:
    """Return the callback URL for a public origin."""
    return public_base_url.rstrip("/") + "/oauth/google/callback"


def state_deadline(seconds: int, now: datetime | None = None) -> datetime:
    """Return the expiry for a new state token."""
    moment = now or utcnow()
    return moment + timedelta(seconds=max(60, seconds))


class GoogleTokenPort(Protocol):
    """Token exchange used by signup. Tests substitute a fake."""

    async def exchange(
        self, code: str, verifier: str, redirect: str
    ) -> tuple[str, str, datetime | None]:
        """Return an access token, refresh token, and expiry."""

    async def profile(self, access_token: str) -> str:
        """Return the mailbox address."""

    async def revoke(self, token: str) -> None:
        """Revoke a refresh token."""


class GoogleWebClient:
    """Exchange, profile, and revoke calls for the web OAuth client."""

    def __init__(self, client_id: str, client_secret: str) -> None:
        """Store the web client credentials."""
        self._client_id = client_id
        self._client_secret = client_secret

    async def exchange(
        self, code: str, verifier: str, redirect: str
    ) -> tuple[str, str, datetime | None]:
        """Exchange an authorization code for tokens."""
        if not self._client_id or not self._client_secret:
            raise ConfigurationError("Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET first.")
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                _TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": redirect,
                    "grant_type": "authorization_code",
                    "code_verifier": verifier,
                },
            )
        if response.status_code != 200:
            raise ConfigurationError("Google rejected the sign-in.")
        payload = response.json()
        access = str(payload.get("access_token", ""))
        refresh = str(payload.get("refresh_token", ""))
        if not access or not refresh:
            raise ConfigurationError("Google did not return a refresh token.")
        expires_in = payload.get("expires_in")
        expiry = None
        if isinstance(expires_in, int):
            expiry = utcnow() + timedelta(seconds=expires_in)
        return access, refresh, expiry

    async def profile(self, access_token: str) -> str:
        """Return the Gmail address for an access token."""
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                _PROFILE_URL, headers={"Authorization": f"Bearer {access_token}"}
            )
        if response.status_code != 200:
            raise ConfigurationError("Google did not return the mailbox address.")
        email = str(response.json().get("emailAddress", "")).strip().lower()
        if "@" not in email:
            raise ConfigurationError("Google did not return the mailbox address.")
        return email

    async def revoke(self, token: str) -> None:
        """Revoke a refresh token. A failure still lets disconnect continue."""
        if not token:
            return
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                await client.post(_REVOKE_URL, data={"token": token})
        except httpx.HTTPError:
            return
