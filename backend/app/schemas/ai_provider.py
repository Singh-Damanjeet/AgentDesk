from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationInfo,
    field_validator,
)

from app.core.ai_providers import (
    GEMINI_PROVIDER,
    OPENROUTER_PROVIDER,
    SUPPORTED_AI_PROVIDERS,
    SUPPORTED_GEMINI_MODELS,
    is_valid_openrouter_model,
)


def _validate_provider(value: str) -> str:
    normalized = value.strip().lower()

    if normalized not in SUPPORTED_AI_PROVIDERS:
        raise ValueError(
            "Unsupported AI provider. Choose Gemini or OpenRouter."
        )

    return normalized


def _validate_model(
    value: str,
    provider: str | None,
) -> str:
    normalized = value.strip()

    if provider == GEMINI_PROVIDER:
        if normalized not in SUPPORTED_GEMINI_MODELS:
            supported_models = ", ".join(
                sorted(SUPPORTED_GEMINI_MODELS)
            )
            raise ValueError(
                f"Unsupported Gemini model. Choose one of: {supported_models}."
            )
        return normalized

    if provider == OPENROUTER_PROVIDER:
        if not is_valid_openrouter_model(normalized):
            raise ValueError(
                "Invalid OpenRouter model slug. Use an author/model ID "
                "such as google/gemma-4-26b-a4b-it."
            )
        return normalized

    raise ValueError("Choose a supported AI provider before selecting a model.")


class AIProviderUpdate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    provider: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=255)
    api_key: SecretStr | None = Field(
        default=None,
        description="Provider API key. It is never returned by the API.",
    )
    embedding_provider: str | None = None
    embedding_model: str | None = None
    enabled: bool = True

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        return _validate_provider(value)

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str, info: ValidationInfo) -> str:
        provider = info.data.get("provider")
        return _validate_model(value, provider)


class AIProviderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider: str
    model: str
    embedding_provider: str | None
    embedding_model: str | None
    enabled: bool
    api_key_configured: bool


class AIConnectionTestRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    provider: str = Field(min_length=1, max_length=100)
    api_key: SecretStr = Field(
        description="Provider API key. It is used only for this server-side test.",
    )
    model: str = Field(min_length=1, max_length=255)

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        return _validate_provider(value)

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str, info: ValidationInfo) -> str:
        provider = info.data.get("provider")
        return _validate_model(value, provider)


class AIConnectionTestResponse(BaseModel):
    success: bool
    message: str
