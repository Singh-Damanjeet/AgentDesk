from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.ai_providers import is_supported_ai_configuration
from app.core.tickets import ACTIVE_TICKET_STATUSES as ACTIVE_TICKET_STATUS_SET
from app.core.widget import DEFAULT_WIDGET_PROJECT_ID
from app.models.ai_provider import AIProvider
from app.models.knowledge_document import KnowledgeDocument
from app.schemas.dashboard import (
    DashboardAIProviderStatus,
    DashboardKnowledgeStatus,
    DashboardOverviewResponse,
    DashboardStorageStatus,
    DashboardSystemStatus,
    DashboardTicketStatus,
    DashboardWidgetStatus,
)
from app.services.ai_provider_service import AIProviderService
from app.services.ticket_service import TicketService, TicketServiceError
from app.services.widget_service import WidgetService, WidgetServiceError


class DashboardServiceError(RuntimeError):
    """Raised when dashboard state cannot be read from the application database."""


class DashboardService:
    ACTIVE_TICKET_STATUSES = ACTIVE_TICKET_STATUS_SET

    @staticmethod
    def get_overview(db: Session) -> DashboardOverviewResponse:
        try:
            provider = AIProviderService.get(db)
            open_ticket_count = TicketService.count(
                db,
                statuses=DashboardService.ACTIVE_TICKET_STATUSES,
            )
            widget_config = WidgetService.get(
                db,
                DEFAULT_WIDGET_PROJECT_ID,
            )
            knowledge_document_count = db.scalar(
                select(func.count(KnowledgeDocument.id))
            )
        except (
            SQLAlchemyError,
            TicketServiceError,
            WidgetServiceError,
        ) as exc:
            db.rollback()
            raise DashboardServiceError(
                "Dashboard data is currently unavailable."
            ) from exc

        return DashboardOverviewResponse(
            ai_provider=DashboardService._get_ai_provider_status(provider),
            storage=DashboardStorageStatus(
                type="sqlite",
                status="ready",
            ),
            knowledge=DashboardKnowledgeStatus(
                document_count=max(knowledge_document_count or 0, 0),
            ),
            tickets=DashboardTicketStatus(
                open_count=max(open_ticket_count or 0, 0),
            ),
            widget=DashboardWidgetStatus(
                configured=bool(
                    widget_config is not None
                    and widget_config.enabled
                    and widget_config.allowed_domains
                )
            ),
            system=DashboardSystemStatus(status="healthy"),
        )

    @staticmethod
    def _get_ai_provider_status(
        provider: AIProvider | None,
    ) -> DashboardAIProviderStatus:
        if provider is None:
            return DashboardAIProviderStatus(configured=False)

        configured = bool(
            provider.enabled
            and provider.encrypted_api_key
            and is_supported_ai_configuration(
                provider.provider,
                provider.model,
            )
        )

        return DashboardAIProviderStatus(
            configured=configured,
            provider=provider.provider,
            model=provider.model,
        )
