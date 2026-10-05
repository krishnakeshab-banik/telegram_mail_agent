"""Replace global unique keys with per-user keys and drop members.

Revision ID: 0006_user_uniques
Revises: 0005_oauth_state
Create Date: 2026-10-05
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_user_uniques"
down_revision = "0005_oauth_state"
branch_labels = None
depends_on = None

# table, legacy single-column unique, composite unique, lookup index to keep
_KEYS = (
    ("emails", ("gmail_message_id",), ("user_id", "gmail_message_id"), "ix_emails_gmail_message_id"),
    ("folders", ("slug",), ("user_id", "slug"), "ix_folders_slug"),
    ("preferences", ("key",), ("user_id", "key"), "ix_preferences_key"),
    ("oauth_tokens", ("provider",), ("user_id", "provider"), "ix_oauth_tokens_provider"),
    ("reply_templates", ("name",), ("user_id", "name"), "ix_reply_templates_name"),
    ("contacts", ("email",), ("user_id", "email"), "ix_contacts_email"),
)


def upgrade() -> None:
    """Allow two users to store the same natural key, and remove members."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "members" in tables:
        op.drop_table("members")
    if "users" in tables:
        columns = {column["name"] for column in inspector.get_columns("users")}
        if "reminders_override_quiet" not in columns:
            op.add_column(
                "users",
                sa.Column(
                    "reminders_override_quiet",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.true(),
                ),
            )
    for table, legacy, composite, index_name in _KEYS:
        if table not in tables:
            continue
        inspector = sa.inspect(bind)
        if "user_id" not in {column["name"] for column in inspector.get_columns(table)}:
            continue
        current = _unique_sets(inspector, table)
        if composite in current and legacy not in current:
            continue
        _swap_unique(inspector, table, legacy, composite, index_name)


def downgrade() -> None:
    """Per-user unique keys are kept. The members table is not restored."""


def _unique_sets(inspector: sa.Inspector, table: str) -> set[tuple[str, ...]]:
    found: set[tuple[str, ...]] = set()
    for index in inspector.get_indexes(table):
        if index.get("unique"):
            found.add(tuple(index.get("column_names") or ()))
    for constraint in inspector.get_unique_constraints(table):
        found.add(tuple(constraint.get("column_names") or ()))
    return {item for item in found if item}


def _swap_unique(
    inspector: sa.Inspector,
    table: str,
    legacy: tuple[str, ...],
    composite: tuple[str, ...],
    index_name: str,
) -> None:
    with op.batch_alter_table(table) as batch:
        for index in inspector.get_indexes(table):
            if index.get("unique") and tuple(index.get("column_names") or ()) == legacy:
                batch.drop_index(str(index["name"]))
        for constraint in inspector.get_unique_constraints(table):
            columns = tuple(constraint.get("column_names") or ())
            name = constraint.get("name")
            if columns == legacy and name:
                batch.drop_constraint(str(name), type_="unique")
        if composite not in _unique_sets(inspector, table):
            batch.create_unique_constraint(_constraint_name(table, composite), list(composite))
    refreshed = sa.inspect(op.get_bind())
    names = {str(index["name"]) for index in refreshed.get_indexes(table)}
    if index_name not in names:
        op.create_index(index_name, table, [legacy[0]], unique=False)


def _constraint_name(table: str, columns: tuple[str, ...]) -> str:
    return ("uq_" + table + "_" + "_".join(columns))[:60]
