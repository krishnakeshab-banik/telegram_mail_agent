"""SQL for preferences."""

from sqlalchemy import select

from app.db.models.preference import Preference
from app.db.repositories.common import BaseRepository


class PreferenceRepository(BaseRepository):
    """Persistence for inspectable preference rows."""

    async def get(self, key: str) -> Preference | None:
        """Return one preference by key."""
        statement = self.restrict(select(Preference).where(Preference.key == key), Preference)
        return await self.session.scalar(statement)

    async def add(self, preference: Preference) -> Preference:
        """Insert a preference."""
        self.stamp(preference)
        self.session.add(preference)
        await self.session.flush()
        return preference

    async def list_all(self) -> list[Preference]:
        """Return every stored preference."""
        statement = self.restrict(select(Preference).order_by(Preference.key), Preference)
        return list(await self.session.scalars(statement))
