from pydantic import BaseModel, ConfigDict, Field


class AIProviderUpdate(BaseModel):
    provider: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=255)

    api_key: str | None = None

    embedding_provider: str | None = None
    embedding_model: str | None = None

    enabled: bool = True


class AIProviderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider: str
    model: str
    embedding_provider: str | None
    embedding_model: str | None
    enabled: bool

    api_key_configured: bool