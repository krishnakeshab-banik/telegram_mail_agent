"""Per-user unique keys and account deletion cover every owned table."""

from datetime import UTC, datetime

from app.db.base import Base, session_scope
from app.db.models.user import User
from app.db.repositories.account_repository import tables_with_user_id
from app.db.repositories.user_repository import UserRepository
from app.db.user_context import user_scope
from app.services.container import Container
from sqlalchemy import func, insert, select, text

_SHARED = {
    "gmail_message_id": "same-message",
    "slug": "same-slug",
    "key": "same-key",
    "provider": "google",
    "name": "same-name",
    "email": "same@example.com",
}


async def test_two_users_can_store_the_same_natural_key_and_delete_is_typed(agent: Container) -> None:
    async with session_scope(agent.sessions) as session:
        names = list(await session.scalars(text("SELECT name FROM sqlite_master WHERE type='table'")))
    assert "members" not in names
    owned = tables_with_user_id()
    assert "emails" in owned
    async with session_scope(agent.sessions) as session:
        second = await UserRepository(session).add(User(telegram_user_id=90, status="active"))
        second_id = second.id
        await _seed(session, 1)
        await _seed(session, second_id)
        before = await _counts(session, 1)
    assert before["emails"] >= 1
    assert before["folders"] >= 1
    with user_scope(second_id):
        await agent.accounts.delete_prompt()
        cancelled = await agent.accounts.accept_text(90, "delete")
    assert cancelled is not None and "cancelled" in cancelled.text
    async with session_scope(agent.sessions) as session:
        assert await UserRepository(session).get_by_telegram(90) is not None
        still = await _counts(session, second_id)
    assert all(count >= 1 for count in still.values())
    with user_scope(second_id):
        await agent.accounts.delete_prompt()
        removed = await agent.accounts.accept_text(90, "DELETE")
    assert removed is not None and "deleted" in removed.text
    async with session_scope(agent.sessions) as session:
        assert await UserRepository(session).get_by_telegram(90) is None
        gone = await _counts(session, second_id)
        kept = await _counts(session, 1)
    assert gone == {name: 0 for name in owned}
    assert kept == before


async def _seed(session: object, user_id: int) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    refs: dict[str, int] = {}
    for table in Base.metadata.sorted_tables:
        if "user_id" not in table.c or table.name == "users":
            continue
        values = {
            column.name: _cell(column, user_id, refs, now)
            for column in table.c
            if not column.primary_key
        }
        result = await session.execute(insert(table).values(**values))  # type: ignore[attr-defined]
        key = result.inserted_primary_key
        if key and key[0] is not None:
            refs[table.name] = int(key[0])


def _cell(column: object, user_id: int, refs: dict[str, int], now: datetime) -> object:
    name = str(getattr(column, "name", ""))
    nullable = bool(getattr(column, "nullable", False))
    if name == "user_id":
        return user_id
    if name in {"email_id", "source_email_id"}:
        return refs["emails"]
    if name == "folder_id":
        return refs["folders"]
    if name == "approval_id" and nullable:
        return None
    if name == "nonce":
        return f"nonce-{user_id}"
    if name.endswith("_json") or name == "value_json":
        return "null"
    if name in _SHARED:
        return _SHARED[name]
    type_name = type(getattr(column, "type", None)).__name__
    if "Date" in type_name or "Time" in type_name:
        return now
    if type_name == "Boolean":
        return False
    if type_name in {"Integer", "BigInteger"}:
        return 1
    if type_name == "Float":
        return 0.0
    if nullable:
        return None
    return "x"


async def _counts(session: object, user_id: int) -> dict[str, int]:
    found: dict[str, int] = {}
    for name in tables_with_user_id():
        table = Base.metadata.tables[name]
        statement = select(func.count()).select_from(table).where(table.c.user_id == user_id)
        found[name] = int(await session.scalar(statement) or 0)  # type: ignore[attr-defined]
    return found
