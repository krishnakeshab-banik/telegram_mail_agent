"""Save and fill reusable replies. Filling a template never sends mail."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import session_scope
from app.db.models.reply_template import ReplyTemplate
from app.db.repositories.template_repository import TemplateRepository


class TemplateService:
    """Store reply templates and substitute {name} and {date}."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Store the session factory."""
        self._sessions = session_factory

    async def list_templates(self) -> list[tuple[str, str]]:
        """Return name and body pairs."""
        async with session_scope(self._sessions) as session:
            rows = await TemplateRepository(session).list_all()
        return [(row.name, row.body) for row in rows]

    async def save(self, name: str, body: str) -> str:
        """Insert or replace a template and return its name."""
        cleaned = name.strip()[:80]
        async with session_scope(self._sessions) as session:
            repo = TemplateRepository(session)
            existing = await repo.get_by_name(cleaned)
            if existing is None:
                await repo.add(ReplyTemplate(name=cleaned, body=body.strip()))
            else:
                existing.body = body.strip()
        return cleaned

    def render(self, body: str, variables: dict[str, str]) -> str:
        """Replace placeholders. Missing values stay as written."""
        rendered = body
        for key, value in variables.items():
            rendered = rendered.replace("{" + key + "}", value)
        return rendered
