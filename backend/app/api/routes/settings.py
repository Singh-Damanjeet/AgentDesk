from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db

from app.schemas.ai_provider import (
    AIConnectionTestRequest,
    AIConnectionTestResponse,
    AIProviderResponse,
    AIProviderUpdate,
)
from app.schemas.company import (
    CompanyResponse,
    CompanyUpdate,
)

from app.services.ai_connection_service import AIConnectionService
from app.services.ai_provider_service import AIProviderService
from app.services.company_service import CompanyService


router = APIRouter(
    prefix="/settings",
    tags=["Settings"],
)


@router.get(
    "/company",
    response_model=CompanyResponse | None,
)
def get_company_settings(
    db: Session = Depends(get_db),
):
    company = CompanyService.get(db)

    if company is None:
        return None

    return company


@router.put(
    "/company",
    response_model=CompanyResponse,
)
def update_company_settings(
    data: CompanyUpdate,
    db: Session = Depends(get_db),
):
    return CompanyService.update(
        db,
        data,
    )


@router.get(
    "/ai",
    response_model=AIProviderResponse | None,
)
def get_ai_settings(
    db: Session = Depends(get_db),
):
    provider = AIProviderService.get(db)

    if provider is None:
        return None

    return AIProviderService.to_response(provider)


@router.put(
    "/ai",
    response_model=AIProviderResponse,
)
def update_ai_settings(
    data: AIProviderUpdate,
    db: Session = Depends(get_db),
):
    try:
        provider = AIProviderService.update(db, data)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return AIProviderService.to_response(provider)


@router.post(
    "/ai/test",
    response_model=AIConnectionTestResponse,
)
async def test_ai_connection(
    data: AIConnectionTestRequest,
):
    success, message = await AIConnectionService.test_connection(
        provider=data.provider,
        api_key=data.api_key.get_secret_value(),
        model=data.model,
    )

    return AIConnectionTestResponse(
        success=success,
        message=message,
    )
