import re


GEMINI_PROVIDER = "gemini"
OPENROUTER_PROVIDER = "openrouter"

SUPPORTED_AI_PROVIDERS = frozenset(
    {
        GEMINI_PROVIDER,
        OPENROUTER_PROVIDER,
    }
)

SUPPORTED_GEMINI_MODELS = frozenset(
    {
        "gemini-3.6-flash",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
    }
)

OPENROUTER_MODEL_SUGGESTIONS = (
    "google/gemma-4-26b-a4b-it",
    "openrouter/free",
)

OPENROUTER_MODEL_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:-]*/"
    r"[A-Za-z0-9][A-Za-z0-9._:-]*$"
)
MAX_OPENROUTER_MODEL_LENGTH = 255


def is_valid_openrouter_model(model: str) -> bool:
    normalized_model = model.strip()
    return (
        bool(normalized_model)
        and len(normalized_model) <= MAX_OPENROUTER_MODEL_LENGTH
        and bool(OPENROUTER_MODEL_PATTERN.fullmatch(normalized_model))
    )


def provider_display_name(provider: str) -> str:
    normalized_provider = provider.strip().lower()
    if normalized_provider == GEMINI_PROVIDER:
        return "Gemini"
    if normalized_provider == OPENROUTER_PROVIDER:
        return "OpenRouter"
    return normalized_provider or "AI provider"


def api_key_label(provider: str) -> str:
    return f"{provider_display_name(provider)} API key"


def is_supported_ai_configuration(
    provider: str,
    model: str,
) -> bool:
    normalized_provider = provider.strip().lower()
    normalized_model = model.strip()

    if normalized_provider == GEMINI_PROVIDER:
        return normalized_model in SUPPORTED_GEMINI_MODELS

    if normalized_provider == OPENROUTER_PROVIDER:
        return is_valid_openrouter_model(normalized_model)

    return False
