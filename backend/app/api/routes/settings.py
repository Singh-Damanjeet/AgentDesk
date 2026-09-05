from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db

from app.schemas.ai_provider import (
    AIProviderResponse,
    AIProviderUpdate,
)
from app.schemas.company import (
    CompanyResponse,
    CompanyUpdate,
)

from app.services.ai_provider_service import (
    AIProviderService,
)
from app.services.company_service import CompanyService


router = APIRouter(
    prefix="/settings",
    tags=["Settings"],
)


@router.get(
    "/company",
    response_model=CompanyResponse,
)
def get_company_settings(
    db: Session = Depends(get_db),
):
    company = CompanyService.get(db)

    if company is None:
        raise HTTPException(
            status_code=404,
            detail="Company configuration not found.",
        )

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
    response_model=AIProviderResponse,
)
def get_ai_settings(
    db: Session = Depends(get_db),
):
    provider = AIProviderService.get(db)

    if provider is None:
        raise HTTPException(
            status_code=404,
            detail="AI provider configuration not found.",
        )

    return AIProviderResponse(
        id=provider.id,
        provider=provider.provider,
        model=provider.model,
        embedding_provider=provider.embedding_provider,
        embedding_model=provider.embedding_model,
        enabled=provider.enabled,
        api_key_configured=bool(
            provider.encrypted_api_key
        ),
    )


@router.put(
    "/ai",
    response_model=AIProviderResponse,
)
def update_ai_settings(
    data: AIProviderUpdate,
    db: Session = Depends(get_db),
):
    provider = AIProviderService.update(
        db,
        data,
    )

    return AIProviderResponse(
        id=provider.id,
        provider=provider.provider,
        model=provider.model,
        embedding_provider=provider.embedding_provider,
        embedding_model=provider.embedding_model,
        enabled=provider.enabled,
        api_key_configured=bool(
            provider.encrypted_api_key
        ),
    )