"""add provider and model fields to agent runs

Revision ID: 9f6e8c7d4b21
Revises: 4b7a22f89266
Create Date: 2026-09-06 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9f6e8c7d4b21"
down_revision: Union[str, Sequence[str], None] = "4b7a22f89266"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable provider metadata for future agent-run records."""
    op.add_column(
        "agent_run",
        sa.Column(
            "provider",
            sa.String(length=100),
            nullable=True,
        ),
    )
    op.add_column(
        "agent_run",
        sa.Column(
            "model",
            sa.String(length=255),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Remove provider metadata from agent runs."""
    op.drop_column("agent_run", "model")
    op.drop_column("agent_run", "provider")
