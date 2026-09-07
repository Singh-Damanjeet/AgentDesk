from app.ai.llm.providers import gemini as gemini_provider
from app.services.ai_service import AIService


# Kept as a module alias so existing integrations/tests that patch the old
# HTTP client path continue to affect the single Gemini adapter implementation.
httpx = gemini_provider.httpx


class AIConnectionService:
    @staticmethod
    async def test_connection(
        provider: str,
        api_key: str,
        model: str,
    ) -> tuple[bool, str]:
        return await AIService.test_connection(
            provider=provider,
            model=model,
            api_key=api_key,
        )
