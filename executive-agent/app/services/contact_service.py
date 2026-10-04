"""Sender profiles and the signals used to personalize importance."""

import re

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.constants import RelationshipType
from app.db.base import session_scope
from app.db.models.contact import Contact
from app.db.repositories.contact_repository import ContactRepository
from app.utils.time import utcnow

_EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")


class ContactService:
    """Maintain one profile per sender and learn from owner actions."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Store the session factory.

        Args:
            session_factory: Database session factory.
        """
        self._sessions = session_factory

    async def observe_message(self, email: str, name: str, category: str) -> Contact:
        """Create or refresh a contact from an inbound or outbound message.

        Args:
            email: Sender or counterpart address.
            name: Display name.
            category: Latest category, stored as a typical topic.

        Returns:
            Updated contact.
        """
        address = email.lower()
        async with session_scope(self._sessions) as session:
            repo = ContactRepository(session)
            contact = await repo.get_by_email(address)
            if contact is None:
                contact = await repo.add(
                    Contact(
                        email=address, display_name=name, relationship_type=RelationshipType.UNKNOWN
                    )
                )
            contact.display_name = name or contact.display_name
            contact.message_count += 1
            contact.last_interaction_at = utcnow()
            topics = [part for part in contact.typical_topics.split(",") if part]
            if category and category not in topics:
                topics.append(category)
            contact.typical_topics = ",".join(topics[:8])
            return contact

    async def get(self, email: str) -> Contact | None:
        """Return a contact profile."""
        async with session_scope(self._sessions) as session:
            return await ContactRepository(session).get_by_email(email.lower())

    async def set_muted(self, email: str, muted: bool) -> str:
        """Mute or unmute a sender.

        Args:
            email: Sender address.
            muted: New mute flag.

        Returns:
            Confirmation text.
        """
        contact = await self._ensure(email)
        async with session_scope(self._sessions) as session:
            stored = await ContactRepository(session).get_by_email(contact.email)
            if stored is not None:
                stored.is_muted = muted
                if muted:
                    stored.priority_weight = min(stored.priority_weight, 0.4)
        verb = "Muted" if muted else "Unmuted"
        return f"{verb} {email.lower()}."

    async def set_vip(self, email: str, vip: bool) -> str:
        """Mark or unmark a VIP sender."""
        contact = await self._ensure(email)
        async with session_scope(self._sessions) as session:
            stored = await ContactRepository(session).get_by_email(contact.email)
            if stored is not None:
                stored.is_vip = vip
                if vip:
                    stored.priority_weight = max(stored.priority_weight, 1.3)
        verb = "Marked VIP" if vip else "Removed VIP"
        return f"{verb}: {email.lower()}."

    async def note_not_important(self, email: str) -> None:
        """Lower a sender's weight after the owner marks a message unimportant."""
        await self._adjust(
            email, factor=0.85, floor=0.3, note="Owner marked a message not important."
        )

    async def note_acted(self, email: str) -> None:
        """Raise a sender's weight slightly when the owner acts on their mail."""
        await self._adjust(email, factor=1.05, ceiling=1.8, note="")

    async def set_relationship(self, email: str, relationship: str) -> None:
        """Store a relationship label when the classifier or owner provides one."""
        if relationship not in {item.value for item in RelationshipType}:
            return
        contact = await self._ensure(email)
        async with session_scope(self._sessions) as session:
            stored = await ContactRepository(session).get_by_email(contact.email)
            if stored is not None:
                stored.relationship_type = relationship

    async def apply_command(self, text: str) -> str | None:
        """Apply a VIP or mute command.

        Args:
            text: Owner message.

        Returns:
            Confirmation, or None when the text is not a contact command.
        """
        match = _EMAIL.search(text)
        if match is None:
            return None
        lowered = text.lower()
        address = match.group(0)
        if lowered.startswith("vip add") or lowered.startswith("vip "):
            if "remove" in lowered:
                return await self.set_vip(address, False)
            return await self.set_vip(address, True)
        if lowered.startswith("mute "):
            return await self.set_muted(address, True)
        if lowered.startswith("unmute "):
            return await self.set_muted(address, False)
        return None

    async def list_vips(self) -> list[str]:
        """Return VIP addresses."""
        async with session_scope(self._sessions) as session:
            return [contact.email for contact in await ContactRepository(session).list_vips()]

    async def list_muted(self) -> list[str]:
        """Return muted addresses."""
        async with session_scope(self._sessions) as session:
            return [contact.email for contact in await ContactRepository(session).list_muted()]

    async def _ensure(self, email: str) -> Contact:
        existing = await self.get(email)
        if existing is not None:
            return existing
        return await self.observe_message(email, "", "other")

    async def _adjust(
        self, email: str, *, factor: float, floor: float = 0.2, ceiling: float = 2.0, note: str
    ) -> None:
        contact = await self._ensure(email)
        async with session_scope(self._sessions) as session:
            stored = await ContactRepository(session).get_by_email(contact.email)
            if stored is None:
                return
            stored.priority_weight = min(ceiling, max(floor, stored.priority_weight * factor))
            if note:
                stored.notes = (stored.notes + "\n" + note).strip()[-1000:]
