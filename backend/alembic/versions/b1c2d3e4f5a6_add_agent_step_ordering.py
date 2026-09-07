"""add deterministic ordering to agent steps

Revision ID: b1c2d3e4f5a6
Revises: a8b2c3d4e5f6
Create Date: 2026-09-07 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "a8b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    op.add_column(
        "agent_step",
        sa.Column("sequence_number", sa.Integer(), nullable=True),
    )

    run_ids = [
        row[0]
        for row in connection.execute(
            sa.text("SELECT DISTINCT agent_run_id FROM agent_step")
        )
    ]
    for run_id in run_ids:
        step_ids = [
            row[0]
            for row in connection.execute(
                sa.text(
                    "SELECT id FROM agent_step "
                    "WHERE agent_run_id = :run_id "
                    "ORDER BY id"
                ),
                {"run_id": run_id},
            )
        ]
        for sequence_number, step_id in enumerate(step_ids, start=1):
            connection.execute(
                sa.text(
                    "UPDATE agent_step SET sequence_number = :sequence_number "
                    "WHERE id = :step_id"
                ),
                {
                    "sequence_number": sequence_number,
                    "step_id": step_id,
                },
            )

    with op.batch_alter_table("agent_step") as batch_op:
        batch_op.alter_column(
            "sequence_number",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.create_unique_constraint(
            "uq_agent_step_run_sequence",
            ["agent_run_id", "sequence_number"],
        )


def downgrade() -> None:
    with op.batch_alter_table("agent_step") as batch_op:
        batch_op.drop_constraint(
            "uq_agent_step_run_sequence",
            type_="unique",
        )
        batch_op.drop_column("sequence_number")
