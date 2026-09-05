from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.system_config import SystemConfig


class ConfigService:
    @staticmethod
    def get_or_create(db: Session) -> SystemConfig:
        config = db.scalar(
            select(SystemConfig).limit(1)
        )

        if config is not None:
            return config

        config = SystemConfig()

        db.add(config)
        db.commit()
        db.refresh(config)

        return config

    @staticmethod
    def get_status(db: Session) -> SystemConfig:
        return ConfigService.get_or_create(db)

    @staticmethod
    def mark_configured(
        db: Session,
        configured: bool = True,
    ) -> SystemConfig:
        config = ConfigService.get_or_create(db)

        config.configured = configured

        db.commit()
        db.refresh(config)

        return config