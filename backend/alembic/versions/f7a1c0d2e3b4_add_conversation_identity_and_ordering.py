"""add conversation identity and deterministic message ordering

Revision ID: f7a1c0d2e3b4
Revises: e2a6c4d8f901
Create Date: 2026-09-06 21:00:00.000000

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f7a1c0d2e3b4"
down_revision: Union[str, Sequence[str], None] = "e2a6c4d8f901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()

    op.add_column(
        "ticket",
        sa.Column("session_id", sa.String(length=100), nullable=True),
    )

    ticket_ids = [
        row[0]
        for row in connection.execute(
            sa.text("SELECT id FROM ticket ORDER BY id")
        )
    ]
    for ticket_id in ticket_ids:
        connection.execute(
            sa.text(
                "UPDATE ticket SET session_id = :session_id "
                "WHERE id = :ticket_id"
            ),
            {
                "session_id": str(uuid.uuid4()),
                "ticket_id": ticket_id,
            },
        )

    with op.batch_alter_table("ticket") as batch_op:
        batch_op.alter_column(
            "session_id",
            existing_type=sa.String(length=100),
            nullable=False,
        )
        batch_op.create_unique_constraint(
            "uq_ticket_session_id",
            ["session_id"],
        )

    op.add_column(
        "message",
        sa.Column("sequence_number", sa.Integer(), nullable=True),
    )

    for ticket_id in ticket_ids:
        message_ids = [
            row[0]
            for row in connection.execute(
                sa.text(
                    "SELECT id FROM message WHERE ticket_id = :ticket_id "
                    "ORDER BY created_at ASC, id ASC"
                ),
                {"ticket_id": ticket_id},
            )
        ]
        for sequence_number, message_id in enumerate(message_ids, start=1):
            connection.execute(
                sa.text(
                    "UPDATE message SET sequence_number = :sequence_number "
                    "WHERE id = :message_id"
                ),
                {
                    "sequence_number": sequence_number,
                    "message_id": message_id,
                },
            )

    with op.batch_alter_table("message") as batch_op:
        batch_op.alter_column(
            "sequence_number",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.create_unique_constraint(
            "uq_message_ticket_sequence",
            ["ticket_id", "sequence_number"],
        )


def downgrade() -> None:
    with op.batch_alter_table("message") as batch_op:
        batch_op.drop_constraint(
            "uq_message_ticket_sequence",
            type_="unique",
        )
        batch_op.drop_column("sequence_number")

    with op.batch_alter_table("ticket") as batch_op:
        batch_op.drop_constraint(
            "uq_ticket_session_id",
            type_="unique",
        )
        batch_op.drop_column("session_id")
