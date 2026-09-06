from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.dashboard import DashboardOverviewResponse
from app.services.dashboard_service import (
    DashboardService,
    DashboardServiceError,
)


router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"],
)


@router.get(
    "/overview",
    response_model=DashboardOverviewResponse,
)
def get_dashboard_overview(
    db: Session = Depends(get_db),
):
    try:
        return DashboardService.get_overview(db)
    except DashboardServiceError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc
