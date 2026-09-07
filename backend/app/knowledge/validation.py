from dataclasses import dataclass
from pathlib import PurePath

from app.knowledge.config import (
    FILE_TYPE_BY_EXTENSION,
    MAX_DOCUMENT_SIZE_BYTES,
)
from app.knowledge.errors import KnowledgeValidationError


MIME_TYPES_BY_FILE_TYPE: dict[str, set[str]] = {
    "pdf": {"application/pdf", "application/octet-stream"},
    "docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
        "application/zip",
    },
    "txt": {"text/plain", "application/octet-stream"},
    "markdown": {
        "text/markdown",
        "text/x-markdown",
        "text/plain",
        "application/octet-stream",
    },
}


@dataclass(frozen=True, slots=True)
class ValidatedUpload:
    filename: str
    file_type: str
    content: bytes


def validate_upload(
    *,
    filename: str | None,
    content_type: str | None,
    content: bytes,
) -> ValidatedUpload:
    normalized_filename = _validate_filename(filename)

    if not content:
        raise KnowledgeValidationError(
            "The uploaded document is empty."
        )

    if len(content) > MAX_DOCUMENT_SIZE_BYTES:
        raise KnowledgeValidationError(
            "The document exceeds the 10 MB upload limit."
        )

    suffix = PurePath(normalized_filename).suffix.lower()
    file_type = FILE_TYPE_BY_EXTENSION.get(suffix)

    if file_type is None:
        raise KnowledgeValidationError(
            "Unsupported document type. Upload a PDF, DOCX, TXT, or Markdown file."
        )

    _validate_content_type(file_type, content_type)

    if file_type in {"txt", "markdown"} and b"\x00" in content:
        raise KnowledgeValidationError(
            "The text document contains unsupported binary content."
        )

    return ValidatedUpload(
        filename=normalized_filename,
        file_type=file_type,
        content=content,
    )


def _validate_content_type(file_type: str, content_type: str | None) -> None:
    if not content_type:
        return

    normalized_content_type = content_type.split(";", 1)[0].strip().lower()
    allowed_types = MIME_TYPES_BY_FILE_TYPE[file_type]

    if file_type in {"txt", "markdown"} and normalized_content_type.startswith(
        "text/"
    ):
        return

    if normalized_content_type not in allowed_types:
        raise KnowledgeValidationError(
            "The uploaded content type does not match its file extension."
        )


def _validate_filename(filename: str | None) -> str:
    if filename is None:
        raise KnowledgeValidationError(
            "A document filename is required."
        )

    normalized_filename = filename.strip()

    if not normalized_filename or normalized_filename in {".", ".."}:
        raise KnowledgeValidationError(
            "A valid document filename is required."
        )

    if len(normalized_filename) > 255:
        raise KnowledgeValidationError(
            "The document filename is too long."
        )

    if any(
        character == "\x00"
        or ord(character) < 32
        or ord(character) == 127
        for character in normalized_filename
    ):
        raise KnowledgeValidationError(
            "The document filename contains invalid characters."
        )

    if "/" in normalized_filename or "\\" in normalized_filename:
        raise KnowledgeValidationError(
            "The document filename must not contain path separators."
        )

    return normalized_filename
