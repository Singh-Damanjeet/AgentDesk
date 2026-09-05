import uuid

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AgentStep(Base):
    __tablename__ = "agent_step"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    agent_run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_run.id"),
        nullable=False,
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

    duration_ms: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )