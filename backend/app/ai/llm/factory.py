from app.ai.llm.base import LLMService
from app.ai.llm.errors import LLMConfigurationError
from app.ai.llm.providers.gemini import GeminiLLMAdapter
from app.ai.llm.providers.openrouter import OpenRouterLLMAdapter
from app.core.ai_providers import (
    GEMINI_PROVIDER,
    OPENROUTER_PROVIDER,
    api_key_label,
)


class LLMFactory:
    """Resolve the configured provider into the shared LLM interface."""

    @staticmethod
    def create(
        provider: str,
        model: str,
        api_key: str,
    ) -> LLMService:
        normalized_provider = provider.strip().lower()

        if normalized_provider not in {
            GEMINI_PROVIDER,
            OPENROUTER_PROVIDER,
        }:
            raise LLMConfigurationError(
                f"Unsupported LLM provider: {normalized_provider}."
            )

        if not api_key.strip():
            raise LLMConfigurationError(
                f"A {api_key_label(normalized_provider)} is required."
            )

        if normalized_provider == GEMINI_PROVIDER:
            return GeminiLLMAdapter(
                api_key=api_key,
                model=model,
            )

        return OpenRouterLLMAdapter(
            api_key=api_key,
            model=model,
        )
