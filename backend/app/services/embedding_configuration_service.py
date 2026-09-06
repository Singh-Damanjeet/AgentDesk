from sqlalchemy.orm import Session

from app.ai.embeddings.base import EmbeddingService
from app.ai.embeddings.factory import EmbeddingFactory
from app.services.ai_provider_service import AIProviderService


class EmbeddingConfigurationService:
    """Resolve embeddings without coupling them to LLM credentials."""

    @staticmethod
    def create(db: Session) -> EmbeddingService:
        provider = AIProviderService.get(db)

        return EmbeddingFactory.create(
            provider=(
                provider.embedding_provider
                if provider is not None
                else None
            ),
            model=(
                provider.embedding_model
                if provider is not None
                else None
            ),
        )
