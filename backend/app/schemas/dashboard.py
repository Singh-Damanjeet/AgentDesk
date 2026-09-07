from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DashboardAIProviderStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    configured: bool
    provider: str | None = None
    model: str | None = None


class DashboardStorageStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["sqlite"]
    status: Literal["ready", "unavailable"]


class DashboardKnowledgeStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_count: int = Field(ge=0)


class DashboardTicketStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    open_count: int = Field(ge=0)


class DashboardWidgetStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    configured: bool


class DashboardSystemStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["healthy", "unavailable"]


class DashboardOverviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ai_provider: DashboardAIProviderStatus
    storage: DashboardStorageStatus
    knowledge: DashboardKnowledgeStatus
    tickets: DashboardTicketStatus
    widget: DashboardWidgetStatus
    system: DashboardSystemStatus
