from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


AgentCategory = Literal[
    "billing",
    "refund",
    "account",
    "technical",
    "shipping",
    "general",
    "other",
]

AgentUrgency = Literal["low", "normal", "high", "urgent"]


class ClassificationResult(BaseModel):
    """The only model-generated routing object accepted by the workflow."""

    model_config = ConfigDict(extra="forbid")

    category: AgentCategory = Field(
        description="The primary support category for the latest message."
    )
    urgency: AgentUrgency = Field(
        description="The urgency stated or reasonably implied by the customer."
    )
    needs_account_data: bool = Field(
        description=(
            "True when answering requires the customer's specific account, "
            "order, payment, subscription, or personal-record data."
        )
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in the classification as a number from 0 to 1.",
    )


class AgentStepResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    sequence_number: int = Field(ge=1)
    step_type: str
    input_summary: str | None
    output_summary: str | None
    metadata: dict[str, object] | None
    duration_ms: float | None


class AgentRunSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    trace_id: str
    ticket_id: str | None
    status: str
    provider: str | None
    model: str | None
    started_at: datetime
    finished_at: datetime | None
    latency_ms: float | None
    error: str | None
    step_count: int = Field(ge=0)


class AgentRunDetailResponse(AgentRunSummaryResponse):
    steps: list[AgentStepResponse]


class AgentRunListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AgentRunSummaryResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
