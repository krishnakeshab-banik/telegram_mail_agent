"""Apply Alembic migrations at startup."""

from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import Settings

_ROOT = Path(__file__).resolve().parents[2]


def upgrade_database(settings: Settings) -> None:
    """Upgrade the database to the latest revision.

    Args:
        settings: Supplies the synchronous database URL.
    """
    config = Config(str(_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_ROOT / "app" / "db" / "migrations"))
    config.set_main_option("sqlalchemy.url", settings.sync_database_url)
    command.upgrade(config, "head")
