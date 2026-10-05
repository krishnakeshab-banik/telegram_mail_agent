"""Process entrypoint. Wires the container, migrations, scheduler, and Telegram bot."""

import asyncio
import sys
from pathlib import Path

from app.bot.app import build_application
from app.config import get_settings
from app.db.migrate import upgrade_database
from app.exceptions import ConfigurationError
from app.health import serve_health
from app.scheduler.scheduler import build_scheduler
from app.services.container import build_container
from app.utils.logging import configure_logging, get_logger

logger = get_logger(__name__)


def main() -> None:
    """Start the agent, or run a boot check when --check is passed."""
    settings = get_settings()
    configure_logging(
        settings.log_level,
        json_output=settings.log_json,
        activity_path=Path("data") / "activity.jsonl",
    )
    _require_config(settings, check_only="--check" in sys.argv)
    Path("data").mkdir(parents=True, exist_ok=True)
    upgrade_database(settings)
    container = build_container(settings)
    application = build_application(container)
    scheduler = build_scheduler(container)
    if "--check" in sys.argv:
        asyncio.run(_check(container, scheduler))
        logger.info("boot_check_ok")
        return
    _install_lifecycle(application, container, scheduler, settings.health_port)
    logger.info("agent_starting", mode=settings.app_mode)
    application.run_polling(drop_pending_updates=True)


def _require_config(settings: object, *, check_only: bool) -> None:
    from app.config import Settings

    if not isinstance(settings, Settings):
        raise ConfigurationError("Settings failed to load.")
    if not settings.fernet_key:
        raise ConfigurationError("FERNET_KEY is required. See SETUP.md.")
    if check_only:
        return
    if not settings.telegram_bot_token:
        raise ConfigurationError("TELEGRAM_BOT_TOKEN is required.")
    if not settings.allowed_user_ids:
        raise ConfigurationError("TELEGRAM_ALLOWED_USER_IDS is required.")


def _install_lifecycle(
    application: object, container: object, scheduler: object, port: int
) -> None:
    from typing import Any

    from telegram.ext import Application

    from app.services.container import Container

    if not isinstance(application, Application) or not isinstance(container, Container):
        raise ConfigurationError("Application wiring failed.")

    async def post_init(app: Application[Any, Any, Any, Any, Any, Any]) -> None:
        from app.db.user_context import user_scope

        owner = await container.users.ensure_owner()
        container.owner_id = owner.id
        container.sender.bind(app.bot)
        with user_scope(owner.id):
            scheduler.start()  # type: ignore[attr-defined]
            app.bot_data["health_server"] = await serve_health(
                port,
                on_oauth=container.accounts.web_callback,
                console=container.settings.console_enabled,
            )
            from app.services.startup_check import run_startup_checks

            await run_startup_checks(container)
            await container.folders.backfill()
            from app.bot.profile import publish_bot_profile

            try:
                await publish_bot_profile(app.bot)
            except Exception as exc:
                logger.warning("bot_profile_update_failed", error_type=type(exc).__name__)

    async def post_shutdown(app: Application[Any, Any, Any, Any, Any, Any]) -> None:
        scheduler.shutdown(wait=False)  # type: ignore[attr-defined]
        server = app.bot_data.get("health_server")
        if server is not None:
            server.close()
            await server.wait_closed()
        await container.aclose()

    application.post_init = post_init
    application.post_shutdown = post_shutdown


async def _check(container: object, scheduler: object) -> None:
    from app.services.container import Container

    if not isinstance(container, Container):
        raise ConfigurationError("Container wiring failed.")
    scheduler.start()  # type: ignore[attr-defined]
    scheduler.shutdown(wait=False)  # type: ignore[attr-defined]
    await container.aclose()


if __name__ == "__main__":
    main()
