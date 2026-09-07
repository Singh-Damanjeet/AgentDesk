from pathlib import Path

from app.knowledge.errors import KnowledgeProcessingError
from app.knowledge.parsers.base import ParsedSection


class TextParser:
    def parse(self, source_path: Path) -> list[ParsedSection]:
        try:
            content = source_path.read_bytes().decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise KnowledgeProcessingError(
                "Unable to decode this text document as UTF-8."
            ) from exc
        except OSError as exc:
            raise KnowledgeProcessingError(
                "The text document could not be read."
            ) from exc

        if not content.strip():
            raise KnowledgeProcessingError(
                "The text document does not contain readable content."
            )

        return [ParsedSection(text=content)]
