from functools import lru_cache

from app.ai.embeddings.base import (
    EmbeddingConfigurationError,
    EmbeddingService,
)
from app.ai.embeddings.local import (
    DEFAULT_EMBEDDING_MODEL,
    LocalEmbeddingService,
)


LOCAL_EMBEDDING_PROVIDER = "local"


class EmbeddingFactory:
    """Resolve the configured embedding provider."""

    @staticmethod
    def create(
        provider: str | None = None,
        model: str | None = None,
    ) -> EmbeddingService:
        normalized_provider = (provider or LOCAL_EMBEDDING_PROVIDER).strip().lower()

        if normalized_provider != LOCAL_EMBEDDING_PROVIDER:
            raise EmbeddingConfigurationError(
                f"Unsupported embedding provider: {normalized_provider}."
            )

        model_name = (
            (model or DEFAULT_EMBEDDING_MODEL).strip()
            or DEFAULT_EMBEDDING_MODEL
        )

        return EmbeddingFactory._create_local(model_name)

    @staticmethod
    @lru_cache(maxsize=4)
    def _create_local(model_name: str) -> EmbeddingService:
        return LocalEmbeddingService(model_name=model_name)
