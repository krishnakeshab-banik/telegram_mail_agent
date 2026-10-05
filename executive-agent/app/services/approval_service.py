"""Confirmation gate. Mutating actions run only after an explicit approval."""

import json
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.constants import ApprovalAction, ApprovalStatus
from app.db.base import session_scope
from app.db.models.approval import Approval
from app.db.repositories.approval_repository import ApprovalRepository
from app.db.user_context import peek_user_id
from app.exceptions import (
    ApprovalExpiredError,
    ApprovalNotFoundError,
    ApprovalStateError,
    UnscopedQueryError,
)
from app.services.audit_service import AuditService
from app.utils.security import decrypt_for_user, encrypt_for_user, payload_hash
from app.utils.time import utcnow

Executor = Callable[[dict[str, Any]], Awaitable[str]]


class ApprovalService:
    """Create, expire, and execute confirmations."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        audit: AuditService,
    ) -> None:
        """Store collaborators.

        Args:
            session_factory: Database session factory.
            settings: Supplies the Fernet key and approval lifetime.
            audit: Append-only action log.
        """
        self._sessions = session_factory
        self._settings = settings
        self._audit = audit
        self._executors: dict[str, Executor] = {}

    def register(self, action: ApprovalAction, executor: Executor) -> None:
        """Register the function that performs an approved action.

        Args:
            action: Action type.
            executor: Coroutine that receives the decrypted payload and returns a result summary.
        """
        self._executors[action.value] = executor

    async def create(
        self,
        *,
        action: ApprovalAction,
        payload: dict[str, Any],
        summary: str,
        source_email_id: int | None,
        telegram_user_id: int | None,
    ) -> int:
        """Store an encrypted pending approval.

        Args:
            action: What will run if the user confirms.
            payload: JSON payload. It is encrypted at rest.
            summary: Redacted description safe to show and audit.
            source_email_id: Related email, when there is one.
            telegram_user_id: Owner who may confirm it.

        Returns:
            New approval id.
        """
        encoded = json.dumps(payload, sort_keys=True, default=str)
        from datetime import timedelta

        user_id = _required_user_id()
        expires = utcnow() + timedelta(minutes=self._settings.approval_ttl_minutes)
        async with session_scope(self._sessions) as session:
            row = await ApprovalRepository(session).add(
                Approval(
                    action_type=action.value,
                    payload_encrypted=encrypt_for_user(encoded, self._settings.fernet_key, user_id),
                    payload_hash=payload_hash(encoded),
                    summary=summary[:400],
                    status=ApprovalStatus.PENDING,
                    source_email_id=source_email_id,
                    telegram_user_id=telegram_user_id,
                    expires_at=expires,
                )
            )
            approval_id = row.id
        await self._audit.record(
            action_type=action.value,
            payload_hash=payload_hash(encoded),
            summary=summary,
            source_email_id=source_email_id,
            approval_id=approval_id,
            approval_status=ApprovalStatus.PENDING,
            result="awaiting confirmation",
        )
        return approval_id

    async def approve(self, approval_id: int, telegram_user_id: int | None = None) -> str:
        """Execute a pending approval exactly once.

        Args:
            approval_id: Approval primary key.

        Returns:
            Result summary from the executor.
        """
        action, payload, source_email_id, digest = await self._claim(approval_id, telegram_user_id)
        executor = self._executors.get(action)
        if executor is None:
            await self._finish(approval_id, ApprovalStatus.FAILED, "No executor is registered.")
            raise ApprovalStateError(f"No executor is registered for {action}.")
        try:
            result = await executor(payload)
        except Exception as exc:
            await self._finish(approval_id, ApprovalStatus.FAILED, str(exc))
            await self._audit.record(
                action_type=action,
                payload_hash=digest,
                summary="Approved action failed.",
                source_email_id=source_email_id,
                approval_id=approval_id,
                approval_status=ApprovalStatus.FAILED,
                result=str(exc),
            )
            raise
        await self._finish(approval_id, ApprovalStatus.APPROVED, result)
        await self._audit.record(
            action_type=action,
            payload_hash=digest,
            summary="Approved action completed.",
            source_email_id=source_email_id,
            approval_id=approval_id,
            approval_status=ApprovalStatus.APPROVED,
            result=result,
        )
        return result

    async def reject(self, approval_id: int, telegram_user_id: int | None = None) -> None:
        """Cancel a pending approval."""
        await self._assert_tapper(approval_id, telegram_user_id)
        await self._transition(approval_id, ApprovalStatus.REJECTED, "Cancelled by the owner.")

    async def expire_due(self) -> int:
        """Expire pending approvals whose lifetime has elapsed."""
        async with session_scope(self._sessions) as session:
            rows = await ApprovalRepository(session).list_expired(utcnow())
            for row in rows:
                row.status = ApprovalStatus.EXPIRED
                row.resolved_at = utcnow()
                row.result_summary = "Expired before confirmation."
            count = len(rows)
        for row_id in [row.id for row in rows]:
            await self._audit.record(
                action_type="approval",
                payload_hash="",
                summary="Approval expired.",
                source_email_id=None,
                approval_id=row_id,
                approval_status=ApprovalStatus.EXPIRED,
                result="expired",
            )
        return count

    async def payload(self, approval_id: int) -> dict[str, Any]:
        """Return the decrypted payload without executing it."""
        async with session_scope(self._sessions) as session:
            row = await self._require(session, approval_id)
            return _decrypt(row.payload_encrypted, self._settings.fernet_key, row.user_id)

    async def summary(self, approval_id: int) -> str:
        """Return the stored summary."""
        async with session_scope(self._sessions) as session:
            return (await self._require(session, approval_id)).summary

    async def _claim(
        self, approval_id: int, telegram_user_id: int | None
    ) -> tuple[str, dict[str, Any], int | None, str]:
        async with session_scope(self._sessions) as session:
            row = await self._require(session, approval_id)
            _check_tapper(row, telegram_user_id)
            self._ensure_pending(row)
            row.status = ApprovalStatus.APPROVED
            row.resolved_at = utcnow()
            return (
                row.action_type,
                _decrypt(row.payload_encrypted, self._settings.fernet_key, row.user_id),
                row.source_email_id,
                row.payload_hash,
            )

    async def _assert_tapper(self, approval_id: int, telegram_user_id: int | None) -> None:
        if telegram_user_id is None:
            return
        async with session_scope(self._sessions) as session:
            row = await self._require(session, approval_id)
            _check_tapper(row, telegram_user_id)

    async def _finish(self, approval_id: int, status: str, result: str) -> None:
        async with session_scope(self._sessions) as session:
            row = await self._require(session, approval_id)
            row.status = status
            row.result_summary = result[:500]
            row.resolved_at = utcnow()

    async def _transition(self, approval_id: int, status: str, result: str) -> None:
        async with session_scope(self._sessions) as session:
            row = await self._require(session, approval_id)
            self._ensure_pending(row)
            row.status = status
            row.result_summary = result
            row.resolved_at = utcnow()
            action = row.action_type
            digest = row.payload_hash
            source = row.source_email_id
        await self._audit.record(
            action_type=action,
            payload_hash=digest,
            summary=result,
            source_email_id=source,
            approval_id=approval_id,
            approval_status=status,
            result=result,
        )

    async def _require(self, session: AsyncSession, approval_id: int) -> Approval:
        row = await ApprovalRepository(session).get(approval_id)
        if row is None:
            raise ApprovalNotFoundError("That approval no longer exists.")
        return row

    def _ensure_pending(self, row: Approval) -> None:
        if row.status != ApprovalStatus.PENDING:
            raise ApprovalStateError("That approval was already resolved.")
        if row.expires_at <= utcnow():
            row.status = ApprovalStatus.EXPIRED
            row.resolved_at = utcnow()
            raise ApprovalExpiredError("That approval expired. Ask again to create a new one.")


def _decrypt(value: str, key: str, user_id: int) -> dict[str, Any]:
    parsed = json.loads(decrypt_for_user(value, key, user_id))
    if not isinstance(parsed, dict):
        raise ApprovalStateError("Approval payload is invalid.")
    return parsed


def _check_tapper(row: Approval, telegram_user_id: int | None) -> None:
    if telegram_user_id is not None and row.telegram_user_id != telegram_user_id:
        raise ApprovalNotFoundError("That approval no longer exists.")


def _required_user_id() -> int:
    user_id = peek_user_id()
    if user_id is None:
        raise UnscopedQueryError("A user id is required to store an approval.")
    return user_id
