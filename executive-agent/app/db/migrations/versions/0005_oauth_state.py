"""Add the web OAuth state table and signup columns on users.

Revision ID: 0005_oauth_state
Revises: 0004_users
Create Date: 2026-10-05
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_oauth_state"
down_revision = "0004_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create oauth_states and the signup columns when they are missing."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "users" in tables:
        columns = {column["name"] for column in inspector.get_columns("users")}
        if "telegram_chat_id" not in columns:
            op.add_column("users", sa.Column("telegram_chat_id", sa.Integer(), nullable=True))
        if "signup_step" not in columns:
            op.add_column(
                "users",
                sa.Column("signup_step", sa.String(16), nullable=False, server_default=""),
            )
    if "oauth_states" in tables:
        return
    op.create_table(
        "oauth_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("nonce", sa.String(64), nullable=False),
        sa.Column("encrypted_verifier", sa.Text(), nullable=False, server_default=""),
        sa.Column("telegram_chat_id", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("nonce"),
    )
    op.create_index("ix_oauth_states_user_id", "oauth_states", ["user_id"])
    op.create_index("ix_oauth_states_nonce", "oauth_states", ["nonce"])
    op.create_index("ix_oauth_states_expires_at", "oauth_states", ["expires_at"])


def downgrade() -> None:
    """OAuth state is not removed automatically."""
    return
