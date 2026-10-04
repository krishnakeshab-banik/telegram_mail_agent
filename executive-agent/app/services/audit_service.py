"""Append-only audit log and redacted operational errors."""

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import session_scope
from app.db.models.audit_log import AuditLog
from app.db.models.job_error import JobError
from app.db.repositories.approval_repository import ApprovalRepository
from app.db.repositories.audit_repository import AuditRepository
from app.db.repositories.email_repository import EmailRepository
from app.db.repositories.state_repository import (
    JobErrorRepository,
    OAuthRepository,
    SyncStateRepository,
)
from app.utils.security import redact
from app.utils.time import utcnow


@dataclass(frozen=True)
class StatusSnapshot:
    """Values shown by /status."""

    paused: bool
    last_sync_at: str
    last_error: str
    queue_size: int
    pending_approvals: int
    errors_24h: int
    mailbox: str
    mode: str = "live"
    google_linked: bool = False
    synced_today: int = 0
    last_gemini_error: str = ""


@dataclass(frozen=True)
class HistoryEntry:
    """One audit row safe to show in Telegram."""

    created_at: str
    action_type: str
    summary: str
    approval_status: str
    result: str


class AuditService:
    """Record user-visible actions and operational failures."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Store the session factory.

        Args:
            session_factory: Database session factory.
        """
        self._sessions = session_factory

    async def record(
        self,
        *,
        action_type: str,
        payload_hash: str,
        summary: str,
        source_email_id: int | None,
        approval_id: int | None,
        approval_status: str,
        result: str,
    ) -> None:
        """Append an audit row. Callers must pass redacted summaries only."""
        async with session_scope(self._sessions) as session:
            await AuditRepository(session).add(
                AuditLog(
                    action_type=action_type,
                    payload_hash=payload_hash,
                    summary=redact(summary)[:500],
                    source_email_id=source_email_id,
                    approval_id=approval_id,
                    approval_status=approval_status,
                    result=redact(result)[:500],
                    actor="user",
                )
            )

    async def record_failure(self, source: str, error: Exception) -> None:
        """Store a redacted job error for /status."""
        async with session_scope(self._sessions) as session:
            await JobErrorRepository(session).add(
                JobError(source=source, message=redact(str(error))[:400])
            )

    async def history(self, limit: int = 12) -> list[HistoryEntry]:
        """Return recent audit entries, newest first."""
        async with session_scope(self._sessions) as session:
            rows = await AuditRepository(session).list_recent(limit)
        return [
            HistoryEntry(
                created_at=row.created_at.strftime("%Y-%m-%d %H:%M UTC"),
                action_type=row.action_type,
                summary=row.summary,
                approval_status=row.approval_status,
                result=row.result,
            )
            for row in rows
        ]

    async def status(self, *, paused: bool, mode: str) -> StatusSnapshot:
        """Build the /status snapshot."""
        since = utcnow() - timedelta(hours=24)
        async with session_scope(self._sessions) as session:
            sync = await SyncStateRepository(session).get_singleton()
            queue = await EmailRepository(session).count_unprocessed()
            pending = len(await ApprovalRepository(session).list_pending())
            errors = await JobErrorRepository(session).count_since(since)
            synced_today = await EmailRepository(session).count_received_since(since)
            token = await OAuthRepository(session).get_google()
        last_sync = (
            sync.last_sync_at.strftime("%Y-%m-%d %H:%M UTC") if sync.last_sync_at else "never"
        )
        linked = bool(token and token.encrypted_refresh_token) or mode == "demo"
        return StatusSnapshot(
            paused=paused,
            last_sync_at=last_sync,
            last_error=sync.last_error,
            queue_size=queue,
            pending_approvals=pending,
            errors_24h=errors,
            mailbox=sync.mailbox_email,
            mode=mode,
            google_linked=linked,
            synced_today=synced_today,
            last_gemini_error=sync.last_gemini_error,
        )
