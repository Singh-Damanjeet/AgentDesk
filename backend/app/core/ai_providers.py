GEMINI_PROVIDER = "gemini"

SUPPORTED_GEMINI_MODELS = frozenset(
    {
        "gemini-2.5-flash",
        "gemini-2.5-pro",
    }
)


def is_supported_ai_configuration(
    provider: str,
    model: str,
) -> bool:
    return (
        provider.strip().lower() == GEMINI_PROVIDER
        and model.strip() in SUPPORTED_GEMINI_MODELS
    )
