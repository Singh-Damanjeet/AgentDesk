import httpx

from app.core.ai_providers import (
    GEMINI_PROVIDER,
    SUPPORTED_GEMINI_MODELS,
)


class AIConnectionService:
    @staticmethod
    async def test_connection(
        provider: str,
        api_key: str,
        model: str,
    ) -> tuple[bool, str]:
        provider = provider.lower().strip()
        model_name = model.removeprefix("models/").strip()
        api_key = api_key.strip()

        if provider != GEMINI_PROVIDER:
            return (
                False,
                f"Provider '{provider}' is not supported yet.",
            )

        if model_name not in SUPPORTED_GEMINI_MODELS:
            return False, "The selected Gemini model is not supported."

        if not api_key:
            return False, "A Gemini API key is required."

        if len(api_key) > 4096:
            return False, "The Gemini API key is too long."

        url = (
            "https://generativelanguage.googleapis.com/"
            f"v1beta/models/{model_name}"
        )

        try:
            async with httpx.AsyncClient(
                timeout=15.0,
            ) as client:
                response = await client.get(
                    url,
                    headers={
                        "x-goog-api-key": api_key,
                    },
                )

            if response.status_code in {400, 401, 403}:
                return (
                    False,
                    "Invalid API key or access denied.",
                )

            if response.status_code == 404:
                return (
                    False,
                    f"Model '{model_name}' was not found.",
                )

            if response.status_code == 429:
                return False, "Gemini rate limit reached. Try again later."

            if response.status_code >= 400:
                return (
                    False,
                    "Gemini connection failed.",
                )

            return (
                True,
                "Gemini connection successful.",
            )

        except httpx.TimeoutException:
            return False, "Connection timed out."

        except httpx.HTTPError:
            return False, "Unable to reach Gemini."
