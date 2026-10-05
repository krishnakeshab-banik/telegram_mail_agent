"""SQL for sync cursors, agent flags, errors, drafts, and conversation state."""

from datetime import datetime

from sqlalchemy import func, select

from app.db.models.agent_state import AgentState
from app.db.models.conversation import ConversationTurn
from app.db.models.draft import DraftReply
from app.db.models.job_error import JobError
from app.db.models.oauth_token import OAuthToken
from app.db.models.pending_interaction import PendingInteraction
from app.db.models.style_note import StyleNote
from app.db.models.sync_state import SyncState
from app.db.repositories.common import BaseRepository, SessionRepository


class SyncStateRepository(BaseRepository):
    """Persistence for the Gmail history cursor."""

    async def get_singleton(self) -> SyncState:
        """Return the single sync row, creating it when absent."""
        existing = await self.session.scalar(self.restrict(select(SyncState), SyncState).limit(1))
        if existing is not None:
            return existing
        created = SyncState()
        self.stamp(created)
        self.session.add(created)
        await self.session.flush()
        return created


class AgentStateRepository(SessionRepository):
    """Persistence for pause state and briefing markers."""

    async def get_singleton(self) -> AgentState:
        """Return the single agent-state row, creating it when absent."""
        existing = await self.session.scalar(select(AgentState).limit(1))
        if existing is not None:
            return existing
        created = AgentState()
        self.session.add(created)
        await self.session.flush()
        return created


class OAuthRepository(BaseRepository):
    """Persistence for encrypted OAuth tokens."""

    async def get_google(self) -> OAuthToken | None:
        """Return the Google token row."""
        statement = self.restrict(
            select(OAuthToken).where(OAuthToken.provider == "google"), OAuthToken
        )
        return await self.session.scalar(statement)

    async def add(self, token: OAuthToken) -> OAuthToken:
        """Insert a token row."""
        self.stamp(token)
        self.session.add(token)
        await self.session.flush()
        return token


class DraftRepository(BaseRepository):
    """Persistence for reply drafts."""

    async def get(self, draft_id: int) -> DraftReply | None:
        """Return one draft."""
        return self.visible(await self.session.get(DraftReply, draft_id))

    async def get_by_approval(self, approval_id: int) -> DraftReply | None:
        """Return the draft linked to an approval."""
        statement = self.restrict(
            select(DraftReply).where(DraftReply.approval_id == approval_id), DraftReply
        )
        return await self.session.scalar(statement)

    async def latest_for_email(self, email_id: int) -> DraftReply | None:
        """Return the newest draft for an email."""
        statement = self.restrict(
            select(DraftReply)
            .where(DraftReply.email_id == email_id)
            .order_by(DraftReply.id.desc()),
            DraftReply,
        )
        return await self.session.scalar(statement)

    async def add(self, draft: DraftReply) -> DraftReply:
        """Insert a draft."""
        self.stamp(draft)
        self.session.add(draft)
        await self.session.flush()
        return draft


class StyleNoteRepository(BaseRepository):
    """Persistence for writing-style notes."""

    async def add(self, note: StyleNote) -> StyleNote:
        """Insert a style note."""
        self.stamp(note)
        self.session.add(note)
        await self.session.flush()
        return note

    async def list_recent(self, limit: int = 8) -> list[StyleNote]:
        """Return the newest style notes."""
        statement = self.restrict(select(StyleNote).order_by(StyleNote.id.desc()), StyleNote).limit(
            limit
        )
        return list(await self.session.scalars(statement))


class ConversationRepository(BaseRepository):
    """Persistence for natural-language follow-up context."""

    async def add(self, turn: ConversationTurn) -> ConversationTurn:
        """Insert a conversation turn."""
        self.stamp(turn)
        self.session.add(turn)
        await self.session.flush()
        return turn

    async def recent(self, telegram_user_id: int, limit: int = 6) -> list[ConversationTurn]:
        """Return the newest turns for a user, oldest first."""
        statement = self.restrict(
            select(ConversationTurn)
            .where(ConversationTurn.telegram_user_id == telegram_user_id)
            .order_by(ConversationTurn.id.desc()),
            ConversationTurn,
        ).limit(limit)
        rows = list(await self.session.scalars(statement))
        rows.reverse()
        return rows


class PendingInteractionRepository(BaseRepository):
    """Persistence for the next-message continuation."""

    async def get_for_user(self, telegram_user_id: int) -> PendingInteraction | None:
        """Return the pending interaction for a Telegram user."""
        statement = self.restrict(
            select(PendingInteraction).where(
                PendingInteraction.telegram_user_id == telegram_user_id
            ),
            PendingInteraction,
        )
        return await self.session.scalar(statement)

    async def add(self, pending: PendingInteraction) -> PendingInteraction:
        """Insert a pending interaction."""
        self.stamp(pending)
        self.session.add(pending)
        await self.session.flush()
        return pending

    async def delete(self, pending: PendingInteraction) -> None:
        """Remove a pending interaction owned by this user."""
        if pending.user_id != self.user_id:
            return
        await self.session.delete(pending)


class JobErrorRepository(SessionRepository):
    """Persistence for redacted job failures."""

    async def add(self, error: JobError) -> JobError:
        """Insert an error row."""
        self.session.add(error)
        await self.session.flush()
        return error

    async def list_recent(self, limit: int = 10) -> list[JobError]:
        """Return the newest job errors."""
        statement = select(JobError).order_by(JobError.id.desc()).limit(limit)
        return list(await self.session.scalars(statement))

    async def count_since(self, moment: datetime) -> int:
        """Count errors recorded after a moment."""
        statement = select(func.count()).select_from(JobError).where(JobError.created_at >= moment)
        return int(await self.session.scalar(statement) or 0)
