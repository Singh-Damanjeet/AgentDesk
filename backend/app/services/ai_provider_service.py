from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.secrets import encrypt_secret
from app.models.ai_provider import AIProvider
from app.schemas.ai_provider import AIProviderResponse, AIProviderUpdate


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

        api_key = (
            data.api_key.get_secret_value().strip()
            if data.api_key is not None
            else None
        )

        if api_key == "":
            api_key = None

        if api_key is not None and len(api_key) > 4096:
            raise ValueError("The Gemini API key is too long.")

        if provider is None and api_key is None:
            raise ValueError("A Gemini API key is required.")

        if (
            provider is not None
            and not provider.encrypted_api_key
            and api_key is None
        ):
            raise ValueError("A Gemini API key is required.")

        values = data.model_dump(
            exclude={"api_key"}
        )

        if provider is None:
            provider = AIProvider(**values)
            db.add(provider)

        else:
            for field, value in values.items():
                setattr(provider, field, value)

        if api_key is not None:
            provider.encrypted_api_key = encrypt_secret(
                api_key
            )

        db.commit()
        db.refresh(provider)

        return provider

    @staticmethod
    def to_response(provider: AIProvider) -> AIProviderResponse:
        return AIProviderResponse(
            id=provider.id,
            provider=provider.provider,
            model=provider.model,
            embedding_provider=provider.embedding_provider,
            embedding_model=provider.embedding_model,
            enabled=provider.enabled,
            api_key_configured=bool(provider.encrypted_api_key),
        )
