from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.tickets import (
    ConversationMessageRequest,
    CreateConversationRequest,
    TicketDetailResponse,
)
from app.services.conversation_service import (
    ConversationBusyError,
    ConversationGenerationError,
    ConversationService,
    ConversationServiceError,
)
from app.services.ticket_service import (
    InvalidTicketStatusTransitionError,
    TicketConflictError,
    TicketNotFoundError,
    TicketServiceError,
    TicketValidationError,
)


router = APIRouter(
    prefix="/conversations",
    tags=["Conversations"],
)

conversation_service = ConversationService()


@router.post(
    "",
    response_model=TicketDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    data: CreateConversationRequest,
    db: Session = Depends(get_db),
) -> TicketDetailResponse:
    try:
        return conversation_service.create_or_reuse_ticket(
            db,
            session_id=data.session_id,
            channel=data.channel,
            subject=data.subject,
            customer=data.customer,
        )
    except TicketNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.user_message,
        ) from exc
    except (TicketConflictError, InvalidTicketStatusTransitionError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.user_message,
        ) from exc
    except TicketValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.user_message,
        ) from exc
    except (ConversationServiceError, TicketServiceError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.user_message,
        ) from exc


@router.get(
    "/{session_id}",
    response_model=TicketDetailResponse,
)
def get_conversation(
    session_id: str,
    db: Session = Depends(get_db),
) -> TicketDetailResponse:
    try:
        return conversation_service.get_conversation(db, session_id)
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


@router.post(
    "/{session_id}/messages",
    response_model=TicketDetailResponse,
)
async def append_conversation_message(
    session_id: str,
    data: ConversationMessageRequest,
    db: Session = Depends(get_db),
) -> TicketDetailResponse:
    try:
        return await conversation_service.append_customer_message(
            db,
            session_id=session_id,
            content=data.content,
        )
    except TicketNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.user_message,
        ) from exc
    except ConversationBusyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.user_message,
        ) from exc
    except (TicketConflictError, InvalidTicketStatusTransitionError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.user_message,
        ) from exc
    except TicketValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.user_message,
        ) from exc
    except ConversationGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.user_message,
        ) from exc
    except (ConversationServiceError, TicketServiceError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.user_message,
        ) from exc
