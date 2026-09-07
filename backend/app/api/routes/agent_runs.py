from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.agent import AgentRunDetailResponse, AgentRunListResponse
from app.services.agent_run_service import (
    AgentRunNotFoundError,
    AgentRunService,
    AgentRunServiceError,
)


router = APIRouter(
    prefix="/agent-runs",
    tags=["Agent runs"],
)


@router.get(
    "",
    response_model=AgentRunListResponse,
)
def list_agent_runs(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> AgentRunListResponse:
    try:
        return AgentRunService.list_runs(
            db,
            limit=limit,
            offset=offset,
        )
    except AgentRunServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.user_message,
        ) from exc


@router.get(
    "/{identifier}",
    response_model=AgentRunDetailResponse,
)
def get_agent_run(
    identifier: str,
    db: Session = Depends(get_db),
) -> AgentRunDetailResponse:
    try:
        return AgentRunService.get_run(db, identifier)
    except AgentRunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.user_message,
        ) from exc
    except AgentRunServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.user_message,
        ) from exc
