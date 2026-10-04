"""SQL for the append-only audit log."""

from sqlalchemy import select

from app.db.models.audit_log import AuditLog
from app.db.repositories.common import BaseRepository


class AuditRepository(BaseRepository):
    """Persistence for audit rows. Rows are inserted, never updated."""

    async def add(self, entry: AuditLog) -> AuditLog:
        """Append an audit entry."""
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def list_recent(self, limit: int = 15) -> list[AuditLog]:
        """Return the newest audit entries."""
        statement = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
        return list(await self.session.scalars(statement))
