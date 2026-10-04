"""SQL for saved reply templates."""

from sqlalchemy import select

from app.db.models.reply_template import ReplyTemplate
from app.db.repositories.common import BaseRepository


class TemplateRepository(BaseRepository):
    """Persistence for reusable replies."""

    async def list_all(self) -> list[ReplyTemplate]:
        """Return every template by name."""
        statement = select(ReplyTemplate).order_by(ReplyTemplate.name)
        return list(await self.session.scalars(statement))

    async def get_by_name(self, name: str) -> ReplyTemplate | None:
        """Return one template."""
        statement = select(ReplyTemplate).where(ReplyTemplate.name == name)
        return await self.session.scalar(statement)

    async def add(self, template: ReplyTemplate) -> ReplyTemplate:
        """Insert a template."""
        self.session.add(template)
        await self.session.flush()
        return template
