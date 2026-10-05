"""SQL for saved reply templates."""

from sqlalchemy import select

from app.db.models.reply_template import ReplyTemplate
from app.db.repositories.common import BaseRepository


class TemplateRepository(BaseRepository):
    """Persistence for reusable replies."""

    async def list_all(self) -> list[ReplyTemplate]:
        """Return every template by name."""
        statement = self.restrict(select(ReplyTemplate).order_by(ReplyTemplate.name), ReplyTemplate)
        return list(await self.session.scalars(statement))

    async def get_by_name(self, name: str) -> ReplyTemplate | None:
        """Return one template."""
        statement = self.restrict(
            select(ReplyTemplate).where(ReplyTemplate.name == name), ReplyTemplate
        )
        return await self.session.scalar(statement)

    async def add(self, template: ReplyTemplate) -> ReplyTemplate:
        """Insert a template."""
        self.stamp(template)
        self.session.add(template)
        await self.session.flush()
        return template
