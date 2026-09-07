import uuid

from sqlalchemy import (
    JSON,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AgentStep(Base):
    __tablename__ = "agent_step"
    __table_args__ = (
        UniqueConstraint(
            "agent_run_id",
            "sequence_number",
            name="uq_agent_step_run_sequence",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    agent_run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_run.id"),
        nullable=False,
    )

    sequence_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    step_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    input_summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    output_summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    step_metadata: Mapped[dict[str, object] | None] = mapped_column(
        "metadata",
        JSON,
        nullable=True,
    )

    duration_ms: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
