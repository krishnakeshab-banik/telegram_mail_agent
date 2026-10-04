"""Run the one-time Google OAuth consent flow and store encrypted tokens."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.constants import GOOGLE_SCOPES
from app.db.base import create_engine, create_session_factory
from app.db.migrate import upgrade_database
from app.google.auth import GoogleAuth
from app.utils.logging import configure_logging
from google_auth_oauthlib.flow import InstalledAppFlow


def main() -> None:
    """Open a local browser, then save the refresh token encrypted at rest."""
    settings = get_settings()
    configure_logging(settings.log_level, json_output=False)
    if not settings.google_client_id or not settings.google_client_secret:
        raise SystemExit("Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env first.")
    if not settings.fernet_key:
        raise SystemExit("Set FERNET_KEY in .env first.")
    upgrade_database(settings)
    flow = InstalledAppFlow.from_client_config(
        _client_config(settings.google_client_id, settings.google_client_secret),
        list(GOOGLE_SCOPES),
    )
    credentials = flow.run_local_server(port=8080, access_type="offline", prompt="consent")
    if not credentials.refresh_token:
        raise SystemExit(
            "Google did not return a refresh token. Remove the app's access and run this again."
        )
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    auth = GoogleAuth(sessions, settings)
    asyncio.run(
        auth.save_tokens(
            access_token=credentials.token or "",
            refresh_token=credentials.refresh_token,
            expiry=credentials.expiry,
            account_email="",
        )
    )
    asyncio.run(engine.dispose())
    print("Google authorization saved. Restart the bot.")


def _client_config(client_id: str, client_secret: str) -> dict[str, dict[str, str]]:
    return {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost:8080/"],
        }
    }


if __name__ == "__main__":
    main()
