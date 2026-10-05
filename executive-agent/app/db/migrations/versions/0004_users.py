"""Add accounts and assign every existing row to user 1.

Revision ID: 0004_users
Revises: 0003_folders
Create Date: 2026-10-05
"""

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0004_users"
down_revision = "0003_folders"
branch_labels = None
depends_on = None

_OWNED = (
    "emails",
    "email_analyses",
    "tasks",
    "deadlines",
    "calendar_events",
    "reminders",
    "followups",
    "approvals",
    "audit_logs",
    "oauth_tokens",
    "contacts",
    "preferences",
    "folders",
    "email_folder_links",
    "opportunity_items",
    "otp_entries",
    "reply_templates",
    "attachments",
    "draft_replies",
    "sync_states",
    "pending_interactions",
    "conversation_turns",
    "style_notes",
)


def upgrade() -> None:
    """Create the users table and stamp existing rows with user 1."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "users" not in set(inspector.get_table_names()):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("telegram_user_id", sa.Integer(), nullable=False),
            sa.Column("telegram_username", sa.String(64), nullable=False, server_default=""),
            sa.Column("google_email", sa.String(320), nullable=False, server_default=""),
            sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Kolkata"),
            sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
            sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("quiet_start", sa.String(5), nullable=False, server_default="22:00"),
            sa.Column("quiet_end", sa.String(5), nullable=False, server_default="07:00"),
            sa.Column("reminder_offsets", sa.String(64), nullable=False, server_default="360,30"),
            sa.Column("briefing_hour", sa.Integer(), nullable=False, server_default="8"),
            sa.Column("briefing_minute", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("wrapup_hour", sa.Integer(), nullable=False, server_default="20"),
            sa.Column("wrapup_minute", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("tone", sa.String(16), nullable=False, server_default="direct"),
            sa.Column("importance_threshold", sa.Integer(), nullable=False, server_default="60"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("consented_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_users_telegram_user_id", "users", ["telegram_user_id"], unique=True)
        op.create_index("ix_users_status", "users", ["status"])
    now = datetime.now(UTC).replace(tzinfo=None)
    existing = bind.execute(sa.text("SELECT id FROM users WHERE id = 1")).first()
    if existing is None:
        columns = {column["name"] for column in sa.inspect(bind).get_columns("users")}
        signup = ", signup_step" if "signup_step" in columns else ""
        signup_value = ", ''" if "signup_step" in columns else ""
        bind.execute(
            sa.text(
                "INSERT INTO users ("
                "id, telegram_user_id, telegram_username, google_email, timezone, status, "
                "is_admin, quiet_start, quiet_end, reminder_offsets, briefing_hour, "
                "briefing_minute, wrapup_hour, wrapup_minute, tone, importance_threshold, "
                f"created_at, consented_at{signup}"
                ") VALUES ("
                "1, 0, '', '', 'Asia/Kolkata', 'active', 1, '22:00', '07:00', '360,30', "
                f"8, 0, 20, 0, 'direct', 60, :now, :now{signup_value})"
            ),
            {"now": now},
        )
    inspector = sa.inspect(bind)
    for table in _OWNED:
        _add_user_id(inspector, table)


def downgrade() -> None:
    """User ownership is not removed automatically."""
    return


def _add_user_id(inspector: sa.Inspector, table: str) -> None:
    if table not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns(table)}
    if "user_id" in columns:
        return
    with op.batch_alter_table(table) as batch:
        batch.add_column(
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id"),
                nullable=False,
                server_default="1",
            )
        )
        batch.create_index(f"ix_{table}_user_id", ["user_id"])
