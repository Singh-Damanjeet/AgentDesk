from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.tickets import MAX_MESSAGE_LENGTH, MessageSenderType, TicketStatus
from app.core.widget import (
    DEFAULT_WIDGET_DISPLAY_NAME,
    DEFAULT_WIDGET_PROJECT_ID,
    DEFAULT_WIDGET_WELCOME_MESSAGE,
    MAX_WIDGET_ALLOWED_DOMAINS,
    MAX_WIDGET_DISPLAY_NAME_LENGTH,
    MAX_WIDGET_PROJECT_ID_LENGTH,
    MAX_WIDGET_WELCOME_MESSAGE_LENGTH,
    WidgetPosition,
    normalize_widget_project_id,
)
from app.widget.origin import (
    OriginValidationError,
    normalize_allowed_origins,
)


class WidgetConfigUpdate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    project_id: str = Field(
        default=DEFAULT_WIDGET_PROJECT_ID,
        min_length=1,
        max_length=MAX_WIDGET_PROJECT_ID_LENGTH,
    )
    display_name: str = Field(
        default=DEFAULT_WIDGET_DISPLAY_NAME,
        min_length=1,
        max_length=MAX_WIDGET_DISPLAY_NAME_LENGTH,
    )
    welcome_message: str = Field(
        default=DEFAULT_WIDGET_WELCOME_MESSAGE,
        min_length=1,
        max_length=MAX_WIDGET_WELCOME_MESSAGE_LENGTH,
    )
    position: WidgetPosition = WidgetPosition.BOTTOM_RIGHT
    enabled: bool = True
    allowed_domains: list[str] = Field(
        default_factory=list,
        max_length=MAX_WIDGET_ALLOWED_DOMAINS,
    )

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, value: str) -> str:
        return normalize_widget_project_id(value)

    @field_validator("allowed_domains")
    @classmethod
    def validate_allowed_domains(cls, value: list[str]) -> list[str]:
        try:
            return normalize_allowed_origins(value)
        except OriginValidationError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("display_name", "welcome_message")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        if not value:
            raise ValueError("Widget text must not be empty.")

        return value


class WidgetConfigResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    project_id: str
    display_name: str
    welcome_message: str
    position: WidgetPosition
    enabled: bool
    allowed_domains: list[str]
    created_at: datetime
    updated_at: datetime


class WidgetPublicConfigResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    display_name: str
    welcome_message: str
    position: WidgetPosition
    enabled: bool


class WidgetSessionRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    project_id: str | None = Field(
        default=None,
        max_length=MAX_WIDGET_PROJECT_ID_LENGTH,
    )


class WidgetMessageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    sequence_number: int = Field(ge=1)
    sender_type: MessageSenderType
    content: str = Field(min_length=1)
    created_at: datetime


class WidgetConversationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    status: TicketStatus
    messages: list[WidgetMessageResponse]


class WidgetMessageRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    content: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)
