"""Add signup members and the Gmail backfill flag.

Revision ID: 0002_signup
Revises: 0001_initial
Create Date: 2026-10-05
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_signup"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add columns and the members table when an older database lacks them."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("sync_states")}
    if "backfill_done" not in columns:
        op.add_column(
            "sync_states",
            sa.Column("backfill_done", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "last_gemini_error" not in columns:
        op.add_column(
            "sync_states",
            sa.Column("last_gemini_error", sa.Text(), nullable=False, server_default=""),
        )
    if "members" in inspector.get_table_names():
        return
    op.create_table(
        "members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_user_id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("account_email", sa.String(320), nullable=False, server_default=""),
        sa.Column("encrypted_access_token", sa.Text(), nullable=False, server_default=""),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=False, server_default=""),
        sa.Column("token_expiry", sa.DateTime(), nullable=True),
        sa.Column("history_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("backfill_done", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_members_telegram_user_id", "members", ["telegram_user_id"], unique=True)


def downgrade() -> None:
    """Remove the signup table and backfill columns."""
    op.drop_index("ix_members_telegram_user_id", table_name="members")
    op.drop_table("members")
    op.drop_column("sync_states", "last_gemini_error")
    op.drop_column("sync_states", "backfill_done")
