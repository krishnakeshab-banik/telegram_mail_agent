"""Add virtual folders, opportunity records, and the OTP vault.

Revision ID: 0003_folders
Revises: 0002_signup
Create Date: 2026-10-05
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_folders"
down_revision = "0002_signup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create folder tables when this database does not already have them."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())
    if "folders" not in existing:
        op.create_table(
            "folders",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("slug", sa.String(64), nullable=False),
            sa.Column("title", sa.String(80), nullable=False),
            sa.Column("notify_mode", sa.String(16), nullable=False, server_default="digest"),
            sa.Column("rule_json", sa.Text(), nullable=False, server_default=""),
            sa.Column("is_custom", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_folders_slug", "folders", ["slug"], unique=True)
    if "email_folder_links" not in existing:
        op.create_table(
            "email_folder_links",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("email_id", sa.Integer(), sa.ForeignKey("emails.id"), nullable=False),
            sa.Column("folder_id", sa.Integer(), sa.ForeignKey("folders.id"), nullable=False),
            sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("status", sa.String(32), nullable=False, server_default="new"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("email_id", "folder_id"),
        )
    if "opportunity_items" not in existing:
        op.create_table(
            "opportunity_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("email_id", sa.Integer(), sa.ForeignKey("emails.id"), nullable=False),
            sa.Column("folder_slug", sa.String(64), nullable=False),
            sa.Column("title", sa.Text(), nullable=False, server_default=""),
            sa.Column("organization", sa.String(200), nullable=False, server_default=""),
            sa.Column("deadline_at", sa.DateTime(), nullable=True),
            sa.Column("link", sa.Text(), nullable=False, server_default=""),
            sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("status", sa.String(32), nullable=False, server_default="new"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    if "reply_templates" not in existing:
        op.create_table(
            "reply_templates",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(80), nullable=False),
            sa.Column("body", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_reply_templates_name", "reply_templates", ["name"], unique=True)
    if "otp_entries" not in existing:
        op.create_table(
            "otp_entries",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("email_id", sa.Integer(), sa.ForeignKey("emails.id"), nullable=False),
            sa.Column("sender", sa.String(320), nullable=False, server_default=""),
            sa.Column("masked_code", sa.String(32), nullable=False, server_default=""),
            sa.Column("encrypted_code", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    """Drop the folder tables."""
    op.drop_index("ix_reply_templates_name", table_name="reply_templates")
    op.drop_table("reply_templates")
    op.drop_table("otp_entries")
    op.drop_table("opportunity_items")
    op.drop_table("email_folder_links")
    op.drop_index("ix_folders_slug", table_name="folders")
    op.drop_table("folders")
