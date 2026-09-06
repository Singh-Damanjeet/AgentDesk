import shutil
import uuid
from pathlib import Path

from app.knowledge.config import (
    KNOWLEDGE_STORAGE_DIR,
    STORAGE_EXTENSION_BY_FILE_TYPE,
)
from app.knowledge.errors import KnowledgeStorageError


class DocumentStorage:
    """Store source files under generated document IDs, never user filenames."""

    def __init__(self, root: Path = KNOWLEDGE_STORAGE_DIR):
        self.root = root

    def source_path(self, document_id: str, file_type: str) -> Path:
        self._validate_document_id(document_id)

        extension = STORAGE_EXTENSION_BY_FILE_TYPE.get(file_type)
        if extension is None:
            raise KnowledgeStorageError(
                "The document storage type is not supported."
            )

        directory = self.root / document_id
        path = directory / f"source.{extension}"
        resolved_root = self.root.resolve()
        resolved_path = path.resolve()

        if resolved_root not in resolved_path.parents:
            raise KnowledgeStorageError(
                "The document storage path is invalid."
            )

        return path

    def save(
        self,
        *,
        document_id: str,
        file_type: str,
        content: bytes,
    ) -> Path:
        path = self.source_path(document_id, file_type)

        try:
            path.parent.mkdir(parents=True, exist_ok=False)
            with path.open("xb") as source_file:
                source_file.write(content)
        except FileExistsError as exc:
            raise KnowledgeStorageError(
                "The document storage location already exists."
            ) from exc
        except OSError as exc:
            self.delete(document_id)
            raise KnowledgeStorageError(
                "The document could not be stored."
            ) from exc

        return path

    def delete(self, document_id: str) -> None:
        self._validate_document_id(document_id)
        directory = self.root / document_id

        try:
            if directory.exists():
                shutil.rmtree(directory)
        except OSError as exc:
            raise KnowledgeStorageError(
                "The document source file could not be removed."
            ) from exc

    @staticmethod
    def _validate_document_id(document_id: str) -> None:
        try:
            uuid.UUID(document_id)
        except (ValueError, AttributeError, TypeError) as exc:
            raise KnowledgeStorageError(
                "The document storage ID is invalid."
            ) from exc
