"""Assign mail to virtual folders and list those views."""

import json
import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.constants import FOLDER_SPECS
from app.db.base import session_scope
from app.db.models.folder import Folder
from app.db.models.opportunity_item import OpportunityItem
from app.db.repositories.analysis_repository import AnalysisRepository
from app.db.repositories.common import loads
from app.db.repositories.deadline_repository import DeadlineRepository
from app.db.repositories.email_repository import EmailRepository
from app.db.repositories.folder_repository import FolderRepository
from app.services.contact_service import ContactService
from app.services.extraction import _usable_task
from app.services.folder_rules import FolderHit, classify_message, phishing_reasons
from app.services.opportunity_service import normalize_status, score_opportunity
from app.services.otp_vault import OtpVault
from app.services.preference_service import PreferenceService
from app.utils.time import describe_age, describe_due, utcnow

_OPPORTUNITY = {"jobs", "hackathons", "events", "scholarships"}
_PAGE = 5


@dataclass(frozen=True)
class FolderCount:
    """Unread-style count for one folder button."""

    slug: str
    title: str
    count: int


@dataclass(frozen=True)
class FolderCard:
    """One compact row inside a folder view."""

    email_id: int
    title: str
    sender: str
    detail: str
    status: str
    opportunity_id: int = 0
    masked_code: str = ""


_STOP_WORDS = {"emails", "email", "from", "my", "the", "and", "for", "a", "an", "with"}


class FolderService:
    """Seed folders, classify mail into them, and page the results."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        contacts: ContactService,
        otp: OtpVault,
        preferences: PreferenceService,
        interests: str = "python, machine learning",
    ) -> None:
        """Store collaborators.

        Args:
            session_factory: Database session factory.
            contacts: VIP lookup.
            otp: Vault used when a code is detected.
            preferences: Interest profile and other owner settings.
            interests: Fallback topics used for match scores.
        """
        self._sessions = session_factory
        self._contacts = contacts
        self._otp = otp
        self._preferences = preferences
        self.interests = interests

    async def ensure_seeded(self) -> None:
        """Insert built-in folders that are not already stored."""
        async with session_scope(self._sessions) as session:
            repo = FolderRepository(session)
            for slug, title, notify in FOLDER_SPECS:
                if await repo.get_by_slug(slug) is None:
                    await repo.add(Folder(slug=slug, title=title, notify_mode=notify))

    async def counts(self) -> list[FolderCount]:
        """Return every folder with its active item count."""
        await self.ensure_seeded()
        async with session_scope(self._sessions) as session:
            repo = FolderRepository(session)
            folders = await repo.list_all()
            totals = await repo.counts()
        return [FolderCount(item.slug, item.title, totals.get(item.slug, 0)) for item in folders]

    async def page(self, slug: str, page_number: int = 0, query: str = "") -> list[FolderCard]:
        """Return one page of cards.

        Args:
            slug: Folder slug.
            page_number: Zero-based page.
            query: Optional case-insensitive filter.

        Returns:
            Up to five cards.
        """
        await self.ensure_seeded()
        async with session_scope(self._sessions) as session:
            repo = FolderRepository(session)
            messages = await repo.messages_for(slug, limit=200, offset=0)
            cards = [_card(message, slug) for message in messages]
            needle = query.casefold()
            if needle:
                cards = [
                    card
                    for card in cards
                    if needle in f"{card.title} {card.sender} {card.detail}".casefold()
                ]
            start = page_number * _PAGE
            chosen = cards[start : start + _PAGE]
            identifiers = [card.email_id for card in chosen]
            opportunities = await repo.opportunities_for_emails(identifiers)
            masks = await repo.otp_masks(identifiers) if slug == "otps" else {}
        by_email: dict[int, OpportunityItem] = {}
        for opportunity in opportunities:
            current = by_email.get(opportunity.email_id)
            if current is None or opportunity.folder_slug == slug:
                by_email[opportunity.email_id] = opportunity
        enriched: list[FolderCard] = []
        for card in chosen:
            item = by_email.get(card.email_id)
            detail = card.detail
            opportunity_id = 0
            masked = masks.get(card.email_id, "")
            if item is not None:
                opportunity_id = item.id
                detail = f"score {item.score} · {item.reason} · {item.status}"
            if masked:
                detail = f"{masked} · {detail}"
            enriched.append(
                FolderCard(
                    card.email_id,
                    card.title,
                    card.sender,
                    detail,
                    card.status,
                    opportunity_id,
                    masked,
                )
            )
        return enriched

    async def organize(self, email_ids: list[int]) -> None:
        """Assign folders for specific messages, then any still unassigned."""
        await self.ensure_seeded()
        for email_id in email_ids:
            await self.assign_email(email_id)
        await self.backfill()
        await self.archive_overdue()

    async def assign_email(self, email_id: int) -> list[str]:
        """Classify one stored email into folders.

        Args:
            email_id: Local email id.

        Returns:
            Assigned slugs, primary first.
        """
        await self.ensure_seeded()
        async with session_scope(self._sessions) as session:
            message = await EmailRepository(session).get(email_id)
            analysis = await AnalysisRepository(session).get_by_email(email_id)
            rules = _parsed_rules(await FolderRepository(session).custom_rules())
            if message is None:
                return []
            subject, body, sender = message.subject, message.body_text, message.sender_email
            bulk = message.is_bulk
            category = analysis.category if analysis else "other"
            reply = bool(analysis and analysis.requires_reply)
            meeting = bool(analysis and loads(analysis.meeting_json, {}).get("title"))
            deadlines = loads(analysis.deadlines_json, []) if analysis else []
            actions = loads(analysis.action_items_json, []) if analysis else []
            due_row = await DeadlineRepository(session).earliest_for_email(email_id)
            due_at = due_row.due_at if due_row is not None else None
        has_task = any(
            isinstance(item, dict) and _usable_task(str(item.get("task", ""))) for item in actions
        )
        contact = await self._contacts.get(sender)
        hits = classify_message(
            subject=subject,
            body=body,
            sender=sender,
            category=category,
            is_bulk=bulk,
            requires_reply=reply,
            has_meeting=meeting,
            has_deadline=bool(deadlines),
            is_vip=bool(contact and contact.is_vip),
            custom_rules=rules,
            has_task=has_task,
        )
        await self._persist(email_id, sender, subject, body, hits, due_at)
        await self._mark_phishing(email_id, subject, body)
        return [hit.slug for hit in hits]

    async def backfill(self) -> int:
        """Assign folders to processed mail that has none yet."""
        await self.ensure_seeded()
        async with session_scope(self._sessions) as session:
            identifiers = await FolderRepository(session).unassigned_ids()
        for email_id in identifiers:
            await self.assign_email(email_id)
        return len(identifiers)

    async def set_status(self, item_id: int, status: str) -> str:
        """Advance an opportunity pipeline status."""
        cleaned = normalize_status(status)
        if not cleaned:
            return ""
        async with session_scope(self._sessions) as session:
            return await FolderRepository(session).set_opportunity_status(item_id, cleaned)

    async def archive_overdue(self) -> int:
        """File overdue deadline mail in Archive and retire its deadlines link."""
        await self.ensure_seeded()
        async with session_scope(self._sessions) as session:
            overdue = await DeadlineRepository(session).list_open_until(utcnow())
            repo = FolderRepository(session)
            archive = await repo.get_by_slug("archive")
            deadlines = await repo.get_by_slug("deadlines")
            if archive is None:
                return 0
            moved = 0
            for item in overdue:
                if item.email_id is None:
                    continue
                await repo.link(item.email_id, archive.id, primary=False, status="archived")
                if deadlines is not None:
                    await repo.set_link_status(item.email_id, deadlines.id, "archived")
                moved += 1
        return moved

    async def create_custom(self, name: str, keywords: list[str]) -> str:
        """Save a confirmed custom folder rule.

        Args:
            name: Folder title and slug source.
            keywords: Words that must appear in future mail.

        Returns:
            Stored slug.
        """
        slug = "".join(ch for ch in name.lower() if ch.isalnum())[:32] or "custom"
        async with session_scope(self._sessions) as session:
            repo = FolderRepository(session)
            existing = await repo.get_by_slug(slug)
            if existing is None:
                await repo.add(
                    Folder(
                        slug=slug,
                        title=name[:80],
                        notify_mode="digest",
                        rule_json=json.dumps(keywords),
                        is_custom=True,
                    )
                )
        return slug

    async def interests_text(self) -> str:
        """Return the saved interest profile, or the fallback list."""
        stored = await self._preferences.extra("interests", self.interests)
        return stored or self.interests

    async def _persist(
        self,
        email_id: int,
        sender: str,
        subject: str,
        body: str,
        hits: list[FolderHit],
        due_at: datetime | None,
    ) -> None:
        interests = await self.interests_text()
        async with session_scope(self._sessions) as session:
            repo = FolderRepository(session)
            for index, hit in enumerate(hits):
                folder = await repo.get_by_slug(hit.slug)
                if folder is None:
                    continue
                await repo.link(email_id, folder.id, primary=index == 0, status=hit.status)
                if (
                    hit.slug in _OPPORTUNITY
                    and await repo.opportunity_for_email(email_id, hit.slug) is None
                ):
                    score, reason = score_opportunity(f"{subject}\n{body}", interests)
                    if due_at is not None:
                        reason = f"{reason}; {describe_due(due_at, utcnow())}"
                    await repo.add_opportunity(
                        OpportunityItem(
                            email_id=email_id,
                            folder_slug=hit.slug,
                            title=subject[:300],
                            organization=sender[:200],
                            deadline_at=due_at,
                            score=score,
                            reason=reason,
                            status="new",
                        )
                    )
        if any(hit.slug == "otps" for hit in hits):
            await self._otp.remember(email_id, sender, f"{subject}\n{body}")

    async def _mark_phishing(self, email_id: int, subject: str, body: str) -> None:
        reasons = phishing_reasons(subject, body)
        if not reasons:
            return
        async with session_scope(self._sessions) as session:
            analysis = await AnalysisRepository(session).get_by_email(email_id)
            if analysis is None:
                return
            analysis.summary = "Suspicious: " + "; ".join(reasons)
            analysis.urgency = "critical"


def _card(message: object, slug: str) -> FolderCard:
    from app.db.models.email import EmailMessage

    if not isinstance(message, EmailMessage):
        raise TypeError("Expected an email.")
    due = ""
    if message.received_at:
        due = describe_age(message.received_at, utcnow())
    return FolderCard(
        email_id=message.id,
        title=message.subject[:120],
        sender=message.sender_name or message.sender_email,
        detail=due,
        status=slug,
    )


def parse_folder_request(text: str) -> tuple[str, list[str]] | None:
    """Read a plain-language create-folder sentence.

    Args:
        text: Owner message such as "create folder Research for professor and arXiv".

    Returns:
        Title and keywords, or None when the sentence is not a folder request.
    """
    match = re.match(r"create folder ([A-Za-z0-9 ]+?) for (.+)", text.strip(), re.IGNORECASE)
    if match is None:
        return None
    words = [
        word
        for word in re.findall(r"[A-Za-z0-9@._-]{3,}", match.group(2))
        if word.casefold() not in _STOP_WORDS
    ]
    return match.group(1).strip(), words


def _parsed_rules(rows: list[tuple[str, str]]) -> list[tuple[str, list[str]]]:
    parsed: list[tuple[str, list[str]]] = []
    for slug, raw in rows:
        try:
            keywords = json.loads(raw) if raw else []
        except json.JSONDecodeError:
            keywords = []
        if isinstance(keywords, list):
            parsed.append((slug, [str(item) for item in keywords]))
    return parsed
