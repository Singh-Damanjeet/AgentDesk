from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.tickets import MessageSenderType, TicketStatus
from app.core.widget import (
    MAX_WIDGET_DISPLAY_NAME_LENGTH,
    MAX_WIDGET_WELCOME_MESSAGE_LENGTH,
    WIDGET_CHANNEL,
    normalize_widget_project_id,
)
from app.models.widget_config import WidgetConfig
from app.schemas.tickets import TicketDetailResponse
from app.schemas.widget import (
    WidgetConfigResponse,
    WidgetConfigUpdate,
    WidgetConversationResponse,
    WidgetMessageResponse,
    WidgetPublicConfigResponse,
)
from app.services.conversation_service import ConversationService
from app.services.ticket_service import TicketService
from app.widget.origin import (
    OriginValidationError,
    normalize_allowed_origins,
    origin_is_allowed,
)


class WidgetServiceError(RuntimeError):
    """Base class for safe widget service errors."""

    def __init__(self, message: str):
        self.user_message = message
        super().__init__(message)


class WidgetNotFoundError(WidgetServiceError):
    """Raised when a widget project or session does not exist."""


class WidgetOriginError(WidgetServiceError):
    """Raised when a request origin is not allowed for a widget project."""


class WidgetDisabledError(WidgetServiceError):
    """Raised when a disabled widget is used for a public operation."""


class WidgetValidationError(WidgetServiceError):
    """Raised when widget configuration or public input is invalid."""


class WidgetService:
    """Manage widget configuration and its public conversation boundary."""

    PUBLIC_MESSAGE_TYPES = frozenset(
        {
            MessageSenderType.CUSTOMER,
            MessageSenderType.AI,
            MessageSenderType.HUMAN,
        }
    )

    def __init__(
        self,
        *,
        conversation_service: ConversationService | None = None,
    ):
        self.conversation_service = (
            conversation_service or ConversationService()
        )

    @staticmethod
    def get(
        db: Session,
        project_id: str,
    ) -> WidgetConfig | None:
        normalized_project_id = WidgetService._normalize_project_id(project_id)
        try:
            return db.scalar(
                select(WidgetConfig).where(
                    WidgetConfig.project_id == normalized_project_id
                )
            )
        except SQLAlchemyError as exc:
            db.rollback()
            raise WidgetServiceError(
                "Widget configuration is currently unavailable."
            ) from exc

    @staticmethod
    def update(
        db: Session,
        data: WidgetConfigUpdate,
    ) -> WidgetConfig:
        project_id = WidgetService._normalize_project_id(data.project_id)
        display_name = WidgetService._normalize_text(
            data.display_name,
            max_length=MAX_WIDGET_DISPLAY_NAME_LENGTH,
            field_name="display name",
        )
        welcome_message = WidgetService._normalize_text(
            data.welcome_message,
            max_length=MAX_WIDGET_WELCOME_MESSAGE_LENGTH,
            field_name="welcome message",
        )

        try:
            allowed_domains = normalize_allowed_origins(
                list(data.allowed_domains)
            )
        except OriginValidationError as exc:
            raise WidgetValidationError(str(exc)) from exc

        config = WidgetService.get(db, project_id)
        if config is None:
            config = WidgetConfig(project_id=project_id)
            db.add(config)

        config.display_name = display_name
        config.welcome_message = welcome_message
        config.position = data.position.value
        config.enabled = data.enabled
        config.allowed_domains = allowed_domains

        try:
            db.commit()
            db.refresh(config)
        except IntegrityError as exc:
            db.rollback()
            raise WidgetServiceError(
                "The widget configuration already exists."
            ) from exc
        except SQLAlchemyError as exc:
            db.rollback()
            raise WidgetServiceError(
                "The widget configuration could not be saved."
            ) from exc

        return config

    @staticmethod
    def to_response(config: WidgetConfig) -> WidgetConfigResponse:
        return WidgetConfigResponse(
            id=config.id,
            project_id=config.project_id,
            display_name=config.display_name,
            welcome_message=config.welcome_message,
            position=config.position,
            enabled=config.enabled,
            allowed_domains=list(config.allowed_domains or []),
            created_at=config.created_at,
            updated_at=config.updated_at,
        )

    def get_public_config(
        self,
        db: Session,
        *,
        project_id: str,
        origin: str | None,
    ) -> WidgetPublicConfigResponse:
        config = self._require_access(
            db,
            project_id=project_id,
            origin=origin,
            require_enabled=False,
        )
        return self._public_config_response(config)

    def create_session(
        self,
        db: Session,
        *,
        project_id: str,
        origin: str | None,
    ) -> WidgetConversationResponse:
        config = self._require_access(
            db,
            project_id=project_id,
            origin=origin,
            require_enabled=True,
        )
        detail = self.conversation_service.create_or_reuse_ticket(
            db,
            session_id=None,
            channel=WIDGET_CHANNEL,
            project_id=config.project_id,
        )
        return self._public_conversation(detail)

    def get_session(
        self,
        db: Session,
        *,
        project_id: str | None,
        session_id: str,
        origin: str | None,
    ) -> WidgetConversationResponse:
        resolved_project_id = self._resolve_session_project_id(
            db,
            project_id=project_id,
            session_id=session_id,
        )
        config = self._require_access(
            db,
            project_id=resolved_project_id,
            origin=origin,
            require_enabled=True,
        )
        detail = self.conversation_service.get_conversation(
            db,
            session_id,
            project_id=config.project_id,
        )
        return self._public_conversation(detail)

    async def append_message(
        self,
        db: Session,
        *,
        project_id: str | None,
        session_id: str,
        content: str,
        origin: str | None,
    ) -> WidgetConversationResponse:
        resolved_project_id = self._resolve_session_project_id(
            db,
            project_id=project_id,
            session_id=session_id,
        )
        config = self._require_access(
            db,
            project_id=resolved_project_id,
            origin=origin,
            require_enabled=True,
        )
        detail = await self.conversation_service.append_customer_message(
            db,
            session_id=session_id,
            project_id=config.project_id,
            content=content,
        )
        return self._public_conversation(detail)

    @staticmethod
    def origin_allowed(
        db: Session,
        *,
        project_id: str,
        origin: str | None,
    ) -> bool:
        try:
            config = WidgetService.get(db, project_id)
        except WidgetServiceError:
            return False

        return bool(
            config is not None
            and origin_is_allowed(
                origin,
                list(config.allowed_domains or []),
            )
        )

    def _require_access(
        self,
        db: Session,
        *,
        project_id: str,
        origin: str | None,
        require_enabled: bool,
    ) -> WidgetConfig:
        config = self.get(db, project_id)
        if config is None:
            raise WidgetNotFoundError("Widget project not found.")

        if not origin_is_allowed(
            origin,
            list(config.allowed_domains or []),
        ):
            raise WidgetOriginError(
                "This website origin is not allowed for the widget."
            )

        if require_enabled and not config.enabled:
            raise WidgetDisabledError("This widget is disabled.")

        return config

    @staticmethod
    def _resolve_session_project_id(
        db: Session,
        *,
        project_id: str | None,
        session_id: str,
    ) -> str:
        if project_id is not None:
            return WidgetService._normalize_project_id(project_id)

        ticket = TicketService.get_by_session(db, session_id)

        if ticket.widget_project_id is None:
            raise WidgetNotFoundError("Widget session not found.")

        return WidgetService._normalize_project_id(ticket.widget_project_id)

    @staticmethod
    def _public_config_response(
        config: WidgetConfig,
    ) -> WidgetPublicConfigResponse:
        return WidgetPublicConfigResponse(
            project_id=config.project_id,
            display_name=config.display_name,
            welcome_message=config.welcome_message,
            position=config.position,
            enabled=config.enabled,
        )

    @staticmethod
    def _public_conversation(
        detail: TicketDetailResponse,
    ) -> WidgetConversationResponse:
        return WidgetConversationResponse(
            session_id=detail.session_id,
            status=detail.status,
            messages=[
                WidgetMessageResponse(
                    id=message.id,
                    sequence_number=message.sequence_number,
                    sender_type=message.sender_type,
                    content=message.content,
                    created_at=message.created_at,
                )
                for message in detail.messages
                if message.sender_type in WidgetService.PUBLIC_MESSAGE_TYPES
            ],
        )

    @staticmethod
    def _normalize_project_id(value: str) -> str:
        try:
            return normalize_widget_project_id(value)
        except ValueError as exc:
            raise WidgetValidationError(str(exc)) from exc

    @staticmethod
    def _normalize_text(
        value: str,
        *,
        max_length: int,
        field_name: str,
    ) -> str:
        normalized = value.strip()
        if not normalized:
            raise WidgetValidationError(
                f"The widget {field_name} must not be empty."
            )
        if len(normalized) > max_length:
            raise WidgetValidationError(
                f"The widget {field_name} is too long."
            )

        return normalized
