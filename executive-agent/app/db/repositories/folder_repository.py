"""SQL for folders, links, opportunities, and OTP rows."""

from sqlalchemy import func, select

from app.db.models.email import EmailMessage
from app.db.models.email_folder_link import EmailFolderLink
from app.db.models.folder import Folder
from app.db.models.opportunity_item import OpportunityItem
from app.db.models.otp_entry import OtpEntry
from app.db.repositories.common import BaseRepository


class FolderRepository(BaseRepository):
    """Persistence for virtual folders."""

    async def get_by_slug(self, slug: str) -> Folder | None:
        """Return one folder."""
        statement = self.restrict(select(Folder).where(Folder.slug == slug), Folder)
        return await self.session.scalar(statement)

    async def list_all(self) -> list[Folder]:
        """Return every folder, built-ins first."""
        statement = self.restrict(select(Folder).order_by(Folder.is_custom, Folder.title), Folder)
        return list(await self.session.scalars(statement))

    async def add(self, folder: Folder) -> Folder:
        """Insert a folder."""
        self.stamp(folder)
        self.session.add(folder)
        await self.session.flush()
        return folder

    async def counts(self) -> dict[str, int]:
        """Count active links per folder slug."""
        statement = self.restrict(
            select(Folder.slug, func.count(EmailFolderLink.id))
            .join(EmailFolderLink, EmailFolderLink.folder_id == Folder.id)
            .where(EmailFolderLink.status != "archived")
            .group_by(Folder.slug),
            Folder,
            EmailFolderLink,
        )
        rows = (await self.session.execute(statement)).all()
        return {str(slug): int(count) for slug, count in rows}

    async def link(self, email_id: int, folder_id: int, *, primary: bool, status: str) -> None:
        """Attach an email to a folder once."""
        statement = self.restrict(
            select(EmailFolderLink).where(
                EmailFolderLink.email_id == email_id,
                EmailFolderLink.folder_id == folder_id,
            ),
            EmailFolderLink,
        )
        existing = await self.session.scalar(statement)
        if existing is not None:
            return
        created = EmailFolderLink(
            email_id=email_id,
            folder_id=folder_id,
            is_primary=primary,
            status=status,
        )
        self.stamp(created)
        self.session.add(created)
        await self.session.flush()

    async def messages_for(self, slug: str, limit: int, offset: int) -> list[EmailMessage]:
        """Return messages in a folder, newest first."""
        statement = (
            self.restrict(
                select(EmailMessage)
                .join(EmailFolderLink, EmailFolderLink.email_id == EmailMessage.id)
                .join(Folder, Folder.id == EmailFolderLink.folder_id)
                .where(Folder.slug == slug, EmailFolderLink.status != "archived"),
                EmailMessage,
                EmailFolderLink,
                Folder,
            )
            .order_by(EmailMessage.received_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(await self.session.scalars(statement))

    async def unassigned_ids(self, limit: int = 50) -> list[int]:
        """Return processed emails that are not in any folder yet."""
        linked = self.restrict(select(EmailFolderLink.email_id), EmailFolderLink)
        statement = self.restrict(
            select(EmailMessage.id).where(
                EmailMessage.processed_at.is_not(None), EmailMessage.id.not_in(linked)
            ),
            EmailMessage,
        ).limit(limit)
        return [int(value) for value in await self.session.scalars(statement)]

    async def add_opportunity(self, item: OpportunityItem) -> OpportunityItem:
        """Insert an opportunity row."""
        self.stamp(item)
        self.session.add(item)
        await self.session.flush()
        return item

    async def opportunity_for_email(self, email_id: int, slug: str) -> OpportunityItem | None:
        """Return the opportunity row for one email and folder."""
        statement = self.restrict(
            select(OpportunityItem).where(
                OpportunityItem.email_id == email_id,
                OpportunityItem.folder_slug == slug,
            ),
            OpportunityItem,
        )
        return await self.session.scalar(statement)

    async def set_opportunity_status(self, item_id: int, status: str) -> str:
        """Move an opportunity along its pipeline."""
        item = self.visible(await self.session.get(OpportunityItem, item_id))
        if item is None:
            return ""
        item.status = status
        return item.title

    async def add_otp(self, entry: OtpEntry) -> OtpEntry:
        """Insert an OTP row."""
        self.stamp(entry)
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def otp_for_email(self, email_id: int) -> OtpEntry | None:
        """Return the OTP row for an email."""
        statement = self.restrict(select(OtpEntry).where(OtpEntry.email_id == email_id), OtpEntry)
        return await self.session.scalar(statement)

    async def set_link_status(self, email_id: int, folder_id: int, status: str) -> None:
        """Update the status of one folder link when it exists."""
        statement = self.restrict(
            select(EmailFolderLink).where(
                EmailFolderLink.email_id == email_id,
                EmailFolderLink.folder_id == folder_id,
            ),
            EmailFolderLink,
        )
        existing = await self.session.scalar(statement)
        if existing is not None:
            existing.status = status

    async def opportunities_for_emails(self, email_ids: list[int]) -> list[OpportunityItem]:
        """Return opportunity rows for the given emails."""
        if not email_ids:
            return []
        statement = self.restrict(
            select(OpportunityItem).where(OpportunityItem.email_id.in_(email_ids)),
            OpportunityItem,
        )
        return list(await self.session.scalars(statement))

    async def otp_masks(self, email_ids: list[int]) -> dict[int, str]:
        """Return masked codes for the given emails."""
        if not email_ids:
            return {}
        statement = self.restrict(
            select(OtpEntry).where(OtpEntry.email_id.in_(email_ids)), OtpEntry
        )
        rows = list(await self.session.scalars(statement))
        return {row.email_id: row.masked_code for row in rows}

    async def custom_rules(self) -> list[tuple[str, str]]:
        """Return custom folder slug and rule JSON."""
        statement = self.restrict(
            select(Folder.slug, Folder.rule_json).where(Folder.is_custom.is_(True)), Folder
        )
        return [
            (str(slug), str(rule)) for slug, rule in (await self.session.execute(statement)).all()
        ]
