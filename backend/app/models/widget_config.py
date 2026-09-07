from datetime import datetime, timezone
import uuid

from sqlalchemy import Boolean, DateTime, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WidgetConfig(Base):
    __tablename__ = "widget_config"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    project_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
    )

    display_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    welcome_message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    position: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )

    allowed_domains: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
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
