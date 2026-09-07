from collections.abc import Sequence
from typing import Protocol


class EmbeddingError(Exception):
    """Base class for safe local embedding errors."""

    def __init__(self, message: str):
        self.user_message = message
        super().__init__(message)


class EmbeddingConfigurationError(EmbeddingError):
    """Raised when the local embedding runtime is not available."""


class EmbeddingInputError(EmbeddingError):
    """Raised when text cannot be embedded."""


class EmbeddingProviderError(EmbeddingError):
    """Raised when the local embedding model fails or returns bad data."""


class EmbeddingService(Protocol):
    async def embed_text(self, text: str) -> list[float]:
        ...

    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        ...
