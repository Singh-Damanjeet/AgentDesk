import re

from app.knowledge.errors import KnowledgeProcessingError
from app.knowledge.parsers.base import ParsedSection


class TextNormalizer:
    """Normalize parser output without removing meaningful boundaries."""

    @staticmethod
    def normalize(sections: list[ParsedSection]) -> list[ParsedSection]:
        normalized_sections: list[ParsedSection] = []

        for section in sections:
            text = TextNormalizer._normalize_text(section.text)
            if not text:
                continue

            normalized_sections.append(
                section.model_copy(update={"text": text})
            )

        if not normalized_sections:
            raise KnowledgeProcessingError(
                "The document does not contain readable content."
            )

        return normalized_sections

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized_lines = []

        for line in text.replace("\r\n", "\n").replace("\r", "\n").split(
            "\n"
        ):
            normalized_lines.append(re.sub(r"[ \t]+", " ", line).strip())

        normalized = "\n".join(normalized_lines)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)

        return normalized.strip()
