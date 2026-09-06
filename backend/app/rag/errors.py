class RAGError(Exception):
    """Base class for safe, user-facing RAG errors."""

    def __init__(self, message: str):
        self.user_message = message
        super().__init__(message)


class RAGValidationError(RAGError):
    """Raised when a question cannot be processed safely."""


class RAGEmbeddingError(RAGError):
    """Raised when the query embedding cannot be generated."""


class RAGRetrievalError(RAGError):
    """Raised when the knowledge vector store cannot be searched."""


class RAGGenerationError(RAGError):
    """Raised when the grounded answer cannot be generated."""


class RAGTraceError(RAGError):
    """Raised when a RAG trace cannot be persisted."""
