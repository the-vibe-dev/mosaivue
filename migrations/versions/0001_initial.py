"""Initial Mosaivue schema.

Revision ID: 0001
Revises: None
"""
from __future__ import annotations

from alembic import op
from mosaivue.db import Base
from mosaivue import models  # noqa: F401

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The initial revision is generated from the pinned v0.1 model metadata. Later
    # revisions must use explicit Alembic operations rather than changing this file.
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
