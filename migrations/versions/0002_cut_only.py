"""Remove unused rotation transition setting.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Revision 0001 creates tables from current model metadata on a fresh install.
    # An upgraded beta database still has the unused transition column.
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("rotation_groups")}
    op.execute("UPDATE rotation_groups SET preconnect = 'next' WHERE preconnect = 'all'")
    if "transition" in columns:
        with op.batch_alter_table("rotation_groups") as batch:
            batch.drop_column("transition")


def downgrade() -> None:
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("rotation_groups")}
    if "transition" not in columns:
        with op.batch_alter_table("rotation_groups") as batch:
            batch.add_column(sa.Column("transition", sa.String(32), nullable=False, server_default="cut"))
