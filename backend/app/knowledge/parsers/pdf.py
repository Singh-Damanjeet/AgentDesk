from pathlib import Path

from app.knowledge.errors import KnowledgeProcessingError
from app.knowledge.parsers.base import ParsedSection


class PDFParser:
    def parse(self, source_path: Path) -> list[ParsedSection]:
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(source_path), strict=False)
        except ImportError as exc:
            raise KnowledgeProcessingError(
                "PDF parsing is not available in this installation."
            ) from exc
        except Exception as exc:
            raise KnowledgeProcessingError(
                "Unable to read this PDF document."
            ) from exc

        if reader.is_encrypted:
            raise KnowledgeProcessingError(
                "Encrypted PDFs are not supported."
            )

        sections: list[ParsedSection] = []

        try:
            for page_number, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                if text.strip():
                    sections.append(
                        ParsedSection(
                            text=text,
                            page=page_number,
                        )
                    )
        except Exception as exc:
            raise KnowledgeProcessingError(
                "Unable to extract readable text from this PDF."
            ) from exc

        if not sections:
            raise KnowledgeProcessingError(
                "Unable to extract readable text from this PDF."
            )

        return sections
