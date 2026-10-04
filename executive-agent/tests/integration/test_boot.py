"""The composition root builds and the scheduler can start."""

from app.bot.app import build_application
from app.config import Settings
from app.scheduler.scheduler import build_scheduler
from app.services.container import Container


async def test_application_registers_commands(agent: Container, settings: Settings) -> None:
    application = build_application(agent)
    command_names: set[str] = set()
    for handler in application.handlers[0]:
        commands = getattr(handler, "commands", None)
        if commands:
            command_names.update(commands)
    assert {"start", "brief", "pause", "history", "search"} <= command_names
    scheduler = build_scheduler(agent)
    scheduler.start()
    scheduler.shutdown(wait=False)
    assert settings.app_mode == "demo"
