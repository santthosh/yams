"""Singleton local configuration; financial tables belong to later revisions."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_workspace"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "local_workspace",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("singleton", sa.SmallInteger(), nullable=False),
        sa.Column("locale", sa.String(35), nullable=False),
        sa.Column("default_benchmark", sa.String(160), nullable=False),
        sa.Column("preferences", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("singleton = 1", name="ck_workspace_singleton"),
        sa.UniqueConstraint("singleton", name="uq_workspace_singleton"),
    )


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is unsupported; restore a verified backup")
