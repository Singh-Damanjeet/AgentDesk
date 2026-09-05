from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.secrets import encrypt_secret
from app.models.ai_provider import AIProvider
from app.schemas.ai_provider import AIProviderUpdate


class AIProviderService:
    @staticmethod
    def get(db: Session) -> AIProvider | None:
        return db.scalar(
            select(AIProvider).limit(1)
        )

    @staticmethod
    def update(
        db: Session,
        data: AIProviderUpdate,
    ) -> AIProvider:
        provider = AIProviderService.get(db)

        values = data.model_dump(
            exclude={"api_key"}
        )

        if provider is None:
            provider = AIProvider(**values)
            db.add(provider)

        else:
            for field, value in values.items():
                setattr(provider, field, value)

        if data.api_key:
            provider.encrypted_api_key = encrypt_secret(
                data.api_key
            )

        db.commit()
        db.refresh(provider)

        return provider