from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.ai_providers import is_supported_ai_configuration
from app.core.tickets import ACTIVE_TICKET_STATUSES as ACTIVE_TICKET_STATUS_SET
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
            knowledge_document_count = db.scalar(
                select(func.count(KnowledgeDocument.id))
            )
        except (SQLAlchemyError, TicketServiceError) as exc:
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
            # The widget is not configurable in the current release.
            widget=DashboardWidgetStatus(configured=False),
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
