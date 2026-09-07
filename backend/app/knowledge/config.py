from dataclasses import dataclass
from pathlib import Path

from app.db.session import DATA_DIR


MAX_DOCUMENT_SIZE_BYTES = 10 * 1024 * 1024
KNOWLEDGE_STORAGE_DIR = DATA_DIR / "knowledge"

FILE_TYPE_BY_EXTENSION = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".txt": "txt",
    ".md": "markdown",
    ".markdown": "markdown",
}

STORAGE_EXTENSION_BY_FILE_TYPE = {
    "pdf": "pdf",
    "docx": "docx",
    "txt": "txt",
    "markdown": "md",
}


@dataclass(frozen=True, slots=True)
class ChunkSettings:
    """Configuration for deterministic, approximate-token chunking."""

    target_tokens: int = 700
    overlap_tokens: int = 100

    def __post_init__(self) -> None:
        if self.target_tokens <= 0:
            raise ValueError("target_tokens must be greater than zero.")

        if self.overlap_tokens < 0:
            raise ValueError("overlap_tokens cannot be negative.")

        if self.overlap_tokens >= self.target_tokens:
            raise ValueError(
                "overlap_tokens must be smaller than target_tokens."
            )


DEFAULT_CHUNK_SETTINGS = ChunkSettings()
