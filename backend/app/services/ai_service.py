from collections.abc import Sequence
from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai.embeddings.base import EmbeddingError, EmbeddingService
from app.ai.embeddings.factory import EmbeddingFactory
from app.ai.llm.base import LLMService
from app.ai.llm.errors import LLMError
from app.ai.llm.factory import LLMFactory
from app.ai.llm.types import ChatMessage, LLMResponse
from app.core.secrets import decrypt_secret
from app.services.ai_provider_service import AIProviderService


SchemaModel = TypeVar("SchemaModel", bound=BaseModel)


class AIConfigurationError(RuntimeError):
    """Raised when the persisted AI configuration cannot be used safely."""


class AIService:
    """Thin facade over configured LLM and embedding provider abstractions."""

    def __init__(
        self,
        llm: LLMService,
        embeddings: EmbeddingService,
    ):
        self._llm = llm
        self._embeddings = embeddings

    @property
    def provider(self) -> str:
        return self._llm.provider

    @property
    def model(self) -> str:
        return self._llm.model

    @classmethod
    def from_configuration(cls, db: Session) -> "AIService":
        provider = AIProviderService.get(db)

        if provider is None:
            raise AIConfigurationError(
                "AI provider configuration is required."
            )

        if not provider.enabled:
            raise AIConfigurationError(
                "The configured AI provider is disabled."
            )

        if not provider.encrypted_api_key:
            raise AIConfigurationError(
                "A Gemini API key is required."
            )

        try:
            api_key = decrypt_secret(provider.encrypted_api_key)
        except Exception as exc:
            raise AIConfigurationError(
                "The configured AI credentials could not be loaded."
            ) from exc

        try:
            llm = LLMFactory.create(
                provider=provider.provider,
                model=provider.model,
                api_key=api_key,
            )
            embeddings = EmbeddingFactory.create(
                provider=provider.embedding_provider,
                model=provider.embedding_model,
            )
        except (LLMError, EmbeddingError) as exc:
            raise AIConfigurationError(exc.user_message) from exc

        return cls(
            llm=llm,
            embeddings=embeddings,
        )

    @staticmethod
    async def test_connection(
        provider: str,
        model: str,
        api_key: str,
    ) -> tuple[bool, str]:
        try:
            llm = LLMFactory.create(
                provider=provider,
                model=model,
                api_key=api_key,
            )
            await llm.test_connection()
        except LLMError as exc:
            return False, exc.user_message

        return True, "Gemini connection successful."

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float | None = None,
        timeout_seconds: float | None = None,
        max_output_tokens: int | None = None,
    ) -> LLMResponse:
        return await self._llm.chat(
            messages,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            max_output_tokens=max_output_tokens,
        )

    async def structured_output(
        self,
        messages: Sequence[ChatMessage],
        schema: type[SchemaModel],
        *,
        temperature: float | None = None,
        timeout_seconds: float | None = None,
        max_output_tokens: int | None = None,
    ) -> SchemaModel:
        return await self._llm.structured_output(
            messages,
            schema,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            max_output_tokens=max_output_tokens,
        )

    async def embed_text(self, text: str) -> list[float]:
        return await self._embeddings.embed_text(text)

    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        return await self._embeddings.embed_batch(texts)
