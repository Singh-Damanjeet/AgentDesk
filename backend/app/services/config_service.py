from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ai_providers import (
    api_key_label,
    is_supported_ai_configuration,
)
from app.models.ai_provider import AIProvider
from app.models.company import Company
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

    @staticmethod
    def complete_setup(db: Session) -> SystemConfig:
        company = db.scalar(
            select(Company).limit(1)
        )

        provider = db.scalar(
            select(AIProvider).limit(1)
        )

        if company is None or not company.name.strip():
            raise ValueError(
                "Company configuration is required."
            )

        if provider is None:
            raise ValueError(
                "AI provider configuration is required."
            )

        if not is_supported_ai_configuration(
            provider.provider,
            provider.model,
        ):
            raise ValueError(
                "The selected AI provider or model is not supported."
            )

        if not provider.encrypted_api_key:
            raise ValueError(
                f"A {api_key_label(provider.provider)} is required."
            )

        return ConfigService.mark_configured(
            db,
            True,
        )
