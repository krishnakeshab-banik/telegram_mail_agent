"""Environment-backed settings. One Settings object is shared by the process."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from the environment and an optional .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: str = ""
    telegram_allowed_user_ids: str = ""
    gemini_api_key: str = ""
    gemini_model_fast: str = "gemini-3.8-flash"
    gemini_model_smart: str = "gemini-3.8-flash"
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8080/"
    fernet_key: str = ""
    database_url: str = "sqlite+aiosqlite:///./data/executive_agent.db"
    poll_interval_minutes: int = 2
    briefing_hour: int = 8
    briefing_minute: int = 0
    wrapup_hour: int = 20
    wrapup_minute: int = 0
    timezone: str = "Asia/Kolkata"
    quiet_hours_start: str = "22:00"
    quiet_hours_end: str = "07:00"
    importance_notify_threshold: int = Field(default=60, ge=0, le=100)
    approval_ttl_minutes: int = 60
    max_attachment_bytes: int = 10_000_000
    app_mode: Literal["live", "demo"] = "live"
    log_level: str = "INFO"
    log_json: bool = True
    apply_gmail_labels: bool = False
    health_port: int = 8081
    followup_nudge_hours: int = 48
    reminder_lead_minutes: str = "1440,120"
    google_requests_per_minute: int = 30
    gemini_requests_per_minute: int = 15
    fixture_dir: str = "tests/fixtures"

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        """Return an uppercase log level name."""
        return value.upper()

    @property
    def allowed_user_ids(self) -> frozenset[int]:
        """Telegram user ids permitted to talk to the bot."""
        parsed: set[int] = set()
        for chunk in self.telegram_allowed_user_ids.split(","):
            stripped = chunk.strip()
            if stripped:
                parsed.add(int(stripped))
        return frozenset(parsed)

    @property
    def reminder_leads(self) -> tuple[int, ...]:
        """Minutes before a due time when reminders should fire."""
        leads = [
            int(part.strip()) for part in self.reminder_lead_minutes.split(",") if part.strip()
        ]
        return tuple(sorted(set(leads), reverse=True))

    @property
    def sync_database_url(self) -> str:
        """SQLAlchemy URL suitable for Alembic's synchronous engine."""
        return self.database_url.replace("sqlite+aiosqlite://", "sqlite://", 1)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
