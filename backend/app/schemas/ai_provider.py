from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.core.ai_providers import (
    GEMINI_PROVIDER,
    SUPPORTED_GEMINI_MODELS,
)


class AIProviderUpdate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    provider: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=255)
    api_key: SecretStr | None = Field(
        default=None,
        description="Gemini API key. It is never returned by the API.",
    )
    embedding_provider: str | None = None
    embedding_model: str | None = None
    enabled: bool = True

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        normalized = value.lower()

        if normalized != GEMINI_PROVIDER:
            raise ValueError(
                "Only the Gemini provider is supported in this release."
            )

        return normalized

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        if value not in SUPPORTED_GEMINI_MODELS:
            supported_models = ", ".join(
                sorted(SUPPORTED_GEMINI_MODELS)
            )
            raise ValueError(
                f"Unsupported Gemini model. Choose one of: {supported_models}."
            )

        return value


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
        description="Gemini API key. It is used only for this server-side test.",
    )
    model: str = Field(min_length=1, max_length=255)

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        normalized = value.lower()

        if normalized != GEMINI_PROVIDER:
            raise ValueError(
                "Only the Gemini provider is supported in this release."
            )

        return normalized

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        if value not in SUPPORTED_GEMINI_MODELS:
            supported_models = ", ".join(
                sorted(SUPPORTED_GEMINI_MODELS)
            )
            raise ValueError(
                f"Unsupported Gemini model. Choose one of: {supported_models}."
            )

        return value


class AIConnectionTestResponse(BaseModel):
    success: bool
    message: str
