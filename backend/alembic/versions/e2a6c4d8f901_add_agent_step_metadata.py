"""add structured metadata to agent steps

Revision ID: e2a6c4d8f901
Revises: d7f4e9a13b20
Create Date: 2026-09-06 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e2a6c4d8f901"
down_revision: Union[str, Sequence[str], None] = "d7f4e9a13b20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_step",
        sa.Column("metadata", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_step", "metadata")
