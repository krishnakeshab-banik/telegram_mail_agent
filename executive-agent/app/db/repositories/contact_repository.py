"""SQL for contact profiles."""

from sqlalchemy import select

from app.db.models.contact import Contact
from app.db.repositories.common import BaseRepository


class ContactRepository(BaseRepository):
    """Persistence for sender profiles."""

    async def get_by_email(self, email: str) -> Contact | None:
        """Return a contact by address."""
        statement = self.restrict(select(Contact).where(Contact.email == email.lower()), Contact)
        return await self.session.scalar(statement)

    async def add(self, contact: Contact) -> Contact:
        """Insert a contact."""
        contact.email = contact.email.lower()
        self.stamp(contact)
        self.session.add(contact)
        await self.session.flush()
        return contact

    async def list_vips(self) -> list[Contact]:
        """Return VIP contacts."""
        statement = self.restrict(
            select(Contact).where(Contact.is_vip.is_(True)).order_by(Contact.email), Contact
        )
        return list(await self.session.scalars(statement))

    async def list_muted(self) -> list[Contact]:
        """Return muted contacts."""
        statement = self.restrict(
            select(Contact).where(Contact.is_muted.is_(True)).order_by(Contact.email), Contact
        )
        return list(await self.session.scalars(statement))
