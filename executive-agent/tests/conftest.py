"""Shared fixtures. Tests use demo mode and never call Google or Gemini."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from app.config import Settings
from app.db.migrate import upgrade_database
from app.services.container import Container, build_container
from cryptography.fernet import Fernet

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Return isolated settings pointing at a temporary database."""
    return Settings(
        telegram_bot_token="0:test",
        telegram_allowed_user_ids="42",
        fernet_key=Fernet.generate_key().decode(),
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        app_mode="demo",
        fixture_dir=str(FIXTURES),
        log_json=False,
        gemini_api_key="",
        health_port=0,
    )


@pytest.fixture
async def agent(settings: Settings, tmp_path: Path) -> AsyncIterator[Container]:
    """Migrate a temporary database and return a demo container."""
    upgrade_database(settings)
    container = build_container(settings, data_dir=tmp_path)
    try:
        yield container
    finally:
        await container.aclose()
