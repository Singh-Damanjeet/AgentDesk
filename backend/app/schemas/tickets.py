from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.tickets import (
    DEFAULT_CONVERSATION_CHANNEL,
    MAX_CHANNEL_LENGTH,
    MAX_MESSAGE_LENGTH,
    MAX_SESSION_ID_LENGTH,
    MessageSenderType,
    TicketPriority,
    TicketStatus,
)


class TicketCustomerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str | None
    email: str | None
    external_customer_id: str | None


class TicketMessageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    sequence_number: int = Field(ge=1)
    sender_type: MessageSenderType
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)
    channel: str = Field(min_length=1, max_length=MAX_CHANNEL_LENGTH)
    created_at: datetime


class AgentTraceRetrievalSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = None
    candidate_count: int = Field(ge=0)
    selected_count: int = Field(ge=0)


class AgentTraceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    status: str
    provider: str | None
    model: str | None
    latency_ms: float | None
    error: str | None
    started_at: datetime
    finished_at: datetime | None
    retrieval: AgentTraceRetrievalSummary | None


class TicketSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    session_id: str
    subject: str | None
    status: TicketStatus
    priority: TicketPriority
    channel: str
    customer: TicketCustomerResponse | None
    last_message_preview: str | None
    message_count: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime


class TicketListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[TicketSummaryResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class TicketStatusUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: TicketStatus


class TicketDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    session_id: str
    subject: str | None
    category: str | None
    status: TicketStatus
    priority: TicketPriority
    channel: str
    customer: TicketCustomerResponse | None
    created_at: datetime
    updated_at: datetime
    messages: list[TicketMessageResponse]
    agent_runs: list[AgentTraceSummary]


class ConversationCustomerInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=320)
    external_customer_id: str | None = Field(default=None, max_length=255)

    @field_validator("name", "email", "external_customer_id")
    @classmethod
    def empty_strings_become_none(cls, value: str | None) -> str | None:
        return value or None


class CreateConversationRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    session_id: str | None = Field(
        default=None,
        max_length=MAX_SESSION_ID_LENGTH,
    )
    channel: str = Field(
        default=DEFAULT_CONVERSATION_CHANNEL,
        min_length=1,
        max_length=MAX_CHANNEL_LENGTH,
    )
    subject: str | None = Field(default=None, max_length=500)
    customer: ConversationCustomerInput | None = None

    @field_validator("session_id", "subject")
    @classmethod
    def empty_optional_strings_become_none(
        cls,
        value: str | None,
    ) -> str | None:
        return value or None


class ConversationMessageRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    content: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        if not value:
            raise ValueError("Message content must not be empty.")

        return value
