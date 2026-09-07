class KnowledgeError(Exception):
    """Base class for safe, user-facing knowledge workflow errors."""

    def __init__(self, message: str):
        self.user_message = message
        super().__init__(message)


class KnowledgeValidationError(KnowledgeError):
    """Raised when an uploaded document cannot be accepted safely."""


class KnowledgeNotFoundError(KnowledgeError):
    """Raised when a requested knowledge document does not exist."""


class KnowledgeStorageError(KnowledgeError):
    """Raised when a document cannot be stored or removed safely."""


class KnowledgeProcessingError(KnowledgeError):
    """Raised when parsing, normalization, chunking, or indexing fails."""
