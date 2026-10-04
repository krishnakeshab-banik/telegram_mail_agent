"""Load the sample mailbox and run the real pipeline without Gmail."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.db.migrate import upgrade_database
from app.services.container import build_container
from app.utils.logging import configure_logging


async def seed() -> None:
    """Sync fixtures, classify them, and print how many messages were stored."""
    settings = get_settings()
    if settings.app_mode != "demo":
        raise SystemExit(
            "Set APP_MODE=demo before seeding. This script does not read a live inbox."
        )
    configure_logging(settings.log_level, json_output=False)
    upgrade_database(settings)
    container = build_container(settings)
    try:
        inserted = await container.sync.sync_inbox()
        processed = await container.pipeline.process_pending()
        for email_id in processed:
            await container.attachments.process_email(email_id)
        print(f"Inserted {len(inserted)} messages and processed {len(processed)}.")
    finally:
        await container.aclose()


if __name__ == "__main__":
    asyncio.run(seed())
