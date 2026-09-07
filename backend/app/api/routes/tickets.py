from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.tickets import TicketStatus
from app.db.session import get_db
from app.schemas.tickets import (
    TicketDetailResponse,
    TicketListResponse,
    TicketStatusUpdateRequest,
)
from app.services.conversation_service import ConversationService
from app.services.ticket_service import (
    InvalidTicketStatusTransitionError,
    TicketNotFoundError,
    TicketService,
    TicketServiceError,
    TicketValidationError,
)


router = APIRouter(
    prefix="/tickets",
    tags=["Tickets"],
)

conversation_service = ConversationService()


@router.get(
    "",
    response_model=TicketListResponse,
)
def list_tickets(
    status_filter: TicketStatus | None = Query(
        default=None,
        alias="status",
    ),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> TicketListResponse:
    try:
        return TicketService.list_tickets(
            db,
            status=status_filter,
            limit=limit,
            offset=offset,
        )
    except TicketValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.user_message,
        ) from exc
    except TicketServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.user_message,
        ) from exc


@router.get(
    "/{ticket_id}",
    response_model=TicketDetailResponse,
)
def get_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
) -> TicketDetailResponse:
    try:
        return conversation_service.get_ticket_detail(db, ticket_id)
    except TicketNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.user_message,
        ) from exc
    except TicketValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.user_message,
        ) from exc
    except TicketServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.user_message,
        ) from exc


@router.patch(
    "/{ticket_id}/status",
    response_model=TicketDetailResponse,
)
def update_ticket_status(
    ticket_id: str,
    data: TicketStatusUpdateRequest,
    db: Session = Depends(get_db),
) -> TicketDetailResponse:
    try:
        TicketService.update_status(db, ticket_id, data.status)
        return conversation_service.get_ticket_detail(db, ticket_id)
    except TicketNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.user_message,
        ) from exc
    except InvalidTicketStatusTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.user_message,
        ) from exc
    except TicketValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.user_message,
        ) from exc
    except TicketServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.user_message,
        ) from exc
