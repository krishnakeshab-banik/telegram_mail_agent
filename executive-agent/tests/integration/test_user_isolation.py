"""Two accounts must never read each other's rows."""

import pytest
from app.constants import ApprovalAction
from app.db.base import session_scope
from app.db.models.contact import Contact
from app.db.models.email import EmailMessage
from app.db.models.folder import Folder
from app.db.models.task import Task
from app.db.models.user import User
from app.db.repositories.approval_repository import ApprovalRepository
from app.db.repositories.contact_repository import ContactRepository
from app.db.repositories.email_repository import EmailRepository
from app.db.repositories.folder_repository import FolderRepository
from app.db.repositories.state_repository import (
    ConversationRepository,
    DraftRepository,
    OAuthRepository,
    StyleNoteRepository,
    SyncStateRepository,
)
from app.db.repositories.task_repository import TaskRepository
from app.db.repositories.user_repository import UserRepository
from app.db.user_context import no_user_scope, user_scope
from app.exceptions import ApprovalNotFoundError, UnscopedQueryError
from app.services.container import Container

_SCOPED = (
    EmailRepository,
    TaskRepository,
    ApprovalRepository,
    ContactRepository,
    FolderRepository,
    SyncStateRepository,
    OAuthRepository,
    DraftRepository,
    StyleNoteRepository,
    ConversationRepository,
)


async def test_owner_is_user_one(agent: Container) -> None:
    assert agent.owner_id == 1
    async with session_scope(agent.sessions) as session:
        owner = await UserRepository(session).get(1)
    assert owner is not None
    assert owner.telegram_user_id == 42
    assert owner.is_admin is True
    assert owner.status == "active"


async def test_repository_without_a_user_is_refused(agent: Container) -> None:
    async with session_scope(agent.sessions) as session:
        with no_user_scope():
            for repository in _SCOPED:
                with pytest.raises(UnscopedQueryError):
                    repository(session)


async def test_emails_tasks_and_folders_stay_inside_one_account(agent: Container) -> None:
    async with session_scope(agent.sessions) as session:
        second = await UserRepository(session).add(User(telegram_user_id=99, status="active"))
        second_id = second.id
        message = await EmailRepository(session, user_id=1).add(
            EmailMessage(gmail_message_id="m-1", thread_id="t-1", subject="owner only")
        )
        await TaskRepository(session, user_id=1).add(Task(title="owner task"))
        await FolderRepository(session, user_id=1).add(
            Folder(slug="jobs", title="Jobs", notify_mode="digest")
        )
        await FolderRepository(session, user_id=second_id).add(
            Folder(slug="jobs", title="Jobs", notify_mode="digest")
        )
        other_mail = EmailRepository(session, user_id=second_id)
        assert await other_mail.get(message.id) is None
        assert await other_mail.get_by_gmail_id("m-1") is None
        assert await other_mail.list_unprocessed() == []
        assert (
            await TaskRepository(session, user_id=second_id).list_open(now=message.received_at)
            == []
        )
        assert await FolderRepository(session, user_id=second_id).get_by_slug("jobs") is not None
        assert len(await FolderRepository(session, user_id=1).list_all()) == 1


async def test_same_contact_address_is_allowed_on_two_accounts(agent: Container) -> None:
    async with session_scope(agent.sessions) as session:
        second = await UserRepository(session).add(User(telegram_user_id=100, status="active"))
        await ContactRepository(session, user_id=1).add(
            Contact(email="shared@example.com", is_vip=True)
        )
        await ContactRepository(session, user_id=second.id).add(
            Contact(email="shared@example.com", is_vip=False)
        )
        owner_contact = await ContactRepository(session, user_id=1).get_by_email(
            "shared@example.com"
        )
        other_contact = await ContactRepository(session, user_id=second.id).get_by_email(
            "shared@example.com"
        )
    assert owner_contact is not None and owner_contact.is_vip is True
    assert other_contact is not None and other_contact.is_vip is False


async def test_another_user_cannot_approve(agent: Container) -> None:
    async with session_scope(agent.sessions) as session:
        second = await UserRepository(session).add(User(telegram_user_id=77, status="active"))
        second_id = second.id
    approval_id = await agent.approvals.create(
        action=ApprovalAction.APPLY_LABEL,
        payload={"email_id": 1, "label": "Later"},
        summary="label",
        source_email_id=None,
        telegram_user_id=42,
    )
    with pytest.raises(ApprovalNotFoundError):
        await agent.approvals.approve(approval_id, telegram_user_id=77)
    with user_scope(second_id):
        with pytest.raises(ApprovalNotFoundError):
            await agent.approvals.approve(approval_id, telegram_user_id=77)
    async with session_scope(agent.sessions) as session:
        stored = await ApprovalRepository(session, user_id=1).get(approval_id)
    assert stored is not None
    assert stored.status == "pending"
