"""add widget configuration and project ownership to tickets

Revision ID: a8b2c3d4e5f6
Revises: f7a1c0d2e3b4
Create Date: 2026-09-07 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a8b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f7a1c0d2e3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ticket",
        sa.Column("widget_project_id", sa.String(length=64), nullable=True),
    )

    op.create_table(
        "widget_config",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("welcome_message", sa.Text(), nullable=False),
        sa.Column("position", sa.String(length=20), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("allowed_domains", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id"),
    )


def downgrade() -> None:
    op.drop_table("widget_config")
    op.drop_column("ticket", "widget_project_id")
