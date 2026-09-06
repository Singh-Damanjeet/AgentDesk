from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.rag.errors import RAGError
from app.rag.schemas import RAGQueryRequest, RAGResponse
from app.rag.service import RAGService


router = APIRouter(
    prefix="/rag",
    tags=["RAG"],
)

rag_service = RAGService()


@router.post(
    "/query",
    response_model=RAGResponse,
)
async def query_rag(
    data: RAGQueryRequest,
    db: Session = Depends(get_db),
) -> RAGResponse:
    try:
        return await rag_service.answer(db, data.question)
    except RAGError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.user_message,
        ) from exc
