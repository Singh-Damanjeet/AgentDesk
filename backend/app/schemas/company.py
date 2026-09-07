from pydantic import BaseModel, ConfigDict, Field


class CompanyUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    website: str | None = None
    industry: str | None = None
    support_name: str | None = None
    default_language: str = "en"
    timezone: str = "UTC"


class CompanyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    website: str | None
    industry: str | None
    support_name: str | None
    default_language: str
    timezone: str