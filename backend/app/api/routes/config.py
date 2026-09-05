from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.config import ConfigStatusResponse
from app.services.config_service import ConfigService


router = APIRouter(
    prefix="/config",
    tags=["Configuration"],
)


@router.get(
    "/status",
    response_model=ConfigStatusResponse,
)
def get_config_status(
    db: Session = Depends(get_db),
):
    return ConfigService.get_status(db)