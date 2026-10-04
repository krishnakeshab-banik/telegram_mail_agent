"""Initial schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-05
"""

from alembic import op

from app.db.base import Base
from app.db import models  # noqa: F401

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create every table from the current metadata."""
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    """Drop every table."""
    Base.metadata.drop_all(bind=op.get_bind())
