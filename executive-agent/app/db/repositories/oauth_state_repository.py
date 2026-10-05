"""SQL for single-use OAuth state rows."""

from sqlalchemy import select

from app.db.models.oauth_state import OAuthState
from app.db.repositories.common import BaseRepository


class OAuthStateRepository(BaseRepository):
    """Persistence for Connect Google attempts."""

    async def add(self, state: OAuthState) -> OAuthState:
        """Insert a state row."""
        self.stamp(state)
        self.session.add(state)
        await self.session.flush()
        return state

    async def get_by_nonce(self, nonce: str) -> OAuthState | None:
        """Return the state row for a nonce belonging to this user."""
        statement = self.restrict(select(OAuthState).where(OAuthState.nonce == nonce), OAuthState)
        return await self.session.scalar(statement)
