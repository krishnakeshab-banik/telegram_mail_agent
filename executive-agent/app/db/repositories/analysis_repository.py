"""SQL for classifier results."""

from sqlalchemy import func, select

from app.db.models.analysis import EmailAnalysis
from app.db.repositories.common import BaseRepository


class AnalysisRepository(BaseRepository):
    """Persistence for email intelligence rows."""

    async def get_by_email(self, email_id: int) -> EmailAnalysis | None:
        """Return the analysis for one message, if it exists."""
        statement = select(EmailAnalysis).where(EmailAnalysis.email_id == email_id)
        return await self.session.scalar(statement)

    async def add(self, analysis: EmailAnalysis) -> EmailAnalysis:
        """Insert an analysis row."""
        self.session.add(analysis)
        await self.session.flush()
        return analysis

    async def category_counts(self) -> dict[str, int]:
        """Count analyzed messages by category."""
        statement = select(EmailAnalysis.category, func.count()).group_by(EmailAnalysis.category)
        rows = (await self.session.execute(statement)).all()
        return {str(category): int(count) for category, count in rows}
