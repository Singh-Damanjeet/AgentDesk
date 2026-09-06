from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.knowledge.config import MAX_DOCUMENT_SIZE_BYTES
from app.knowledge.errors import (
    KnowledgeNotFoundError,
    KnowledgeStorageError,
    KnowledgeValidationError,
)
from app.models.knowledge_chunk import KnowledgeChunk
from app.schemas.knowledge import (
    KnowledgeDocumentDetailResponse,
    KnowledgeDocumentResponse,
)
from app.services.knowledge_service import KnowledgeService


router = APIRouter(
    prefix="/knowledge",
    tags=["Knowledge"],
)

knowledge_service = KnowledgeService()


@router.post(
    "/documents",
    response_model=KnowledgeDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_knowledge_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> KnowledgeDocumentResponse:
    try:
        content = await file.read(MAX_DOCUMENT_SIZE_BYTES + 1)
        if len(content) > MAX_DOCUMENT_SIZE_BYTES:
            raise KnowledgeValidationError(
                "The document exceeds the 10 MB upload limit."
            )

        document = await knowledge_service.ingest(
            db,
            filename=file.filename,
            content_type=file.content_type,
            content=content,
        )
        return knowledge_service.to_response(
            document,
            _chunk_count(db, document.id),
        )
    except KnowledgeValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.user_message,
        ) from exc
    except KnowledgeStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=exc.user_message,
        ) from exc


@router.get(
    "/documents",
    response_model=list[KnowledgeDocumentResponse],
)
def list_knowledge_documents(
    db: Session = Depends(get_db),
) -> list[KnowledgeDocumentResponse]:
    return knowledge_service.list_documents(db)


@router.get(
    "/documents/{document_id}",
    response_model=KnowledgeDocumentDetailResponse,
)
def get_knowledge_document(
    document_id: str,
    db: Session = Depends(get_db),
) -> KnowledgeDocumentDetailResponse:
    try:
        return knowledge_service.get_document(db, document_id)
    except KnowledgeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.user_message,
        ) from exc


@router.post(
    "/documents/{document_id}/reindex",
    response_model=KnowledgeDocumentResponse,
)
async def reindex_knowledge_document(
    document_id: str,
    db: Session = Depends(get_db),
) -> KnowledgeDocumentResponse:
    try:
        document = await knowledge_service.reindex(db, document_id)
        return knowledge_service.to_response(
            document,
            _chunk_count(db, document.id),
        )
    except KnowledgeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.user_message,
        ) from exc


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_knowledge_document(
    document_id: str,
    db: Session = Depends(get_db),
) -> None:
    try:
        knowledge_service.delete(db, document_id)
    except KnowledgeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.user_message,
        ) from exc
    except KnowledgeStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=exc.user_message,
        ) from exc


def _chunk_count(db: Session, document_id: str) -> int:
    return int(
        db.scalar(
            select(func.count(KnowledgeChunk.id)).where(
                KnowledgeChunk.document_id == document_id
            )
        )
        or 0
    )
