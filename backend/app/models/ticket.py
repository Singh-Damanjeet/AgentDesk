from datetime import datetime, timezone
import uuid

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.tickets import TicketPriority, TicketStatus
from app.db.base import Base


class Ticket(Base):
    __tablename__ = "ticket"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            name="uq_ticket_session_id",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    customer_id: Mapped[str | None] = mapped_column(
        ForeignKey("customer.id"),
        nullable=True,
    )

    widget_project_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    session_id: Mapped[str] = mapped_column(
        String(100),
        default=lambda: str(uuid.uuid4()),
        nullable=False,
    )

    channel: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    subject: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    category: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default=TicketStatus.OPEN.value,
        nullable=False,
    )

    priority: Mapped[str] = mapped_column(
        String(50),
        default=TicketPriority.NORMAL.value,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
