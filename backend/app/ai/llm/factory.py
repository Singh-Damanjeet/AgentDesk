from app.ai.llm.base import LLMService
from app.ai.llm.errors import LLMConfigurationError
from app.ai.llm.providers.gemini import GeminiLLMAdapter
from app.core.ai_providers import GEMINI_PROVIDER


class LLMFactory:
    """Resolve the configured provider into the shared LLM interface."""

    @staticmethod
    def create(
        provider: str,
        model: str,
        api_key: str,
    ) -> LLMService:
        normalized_provider = provider.strip().lower()

        if normalized_provider != GEMINI_PROVIDER:
            raise LLMConfigurationError(
                f"Unsupported LLM provider: {normalized_provider}."
            )

        if not api_key.strip():
            raise LLMConfigurationError(
                "A Gemini API key is required."
            )

        return GeminiLLMAdapter(
            api_key=api_key,
            model=model,
        )
