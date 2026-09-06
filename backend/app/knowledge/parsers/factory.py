from app.knowledge.errors import KnowledgeProcessingError
from app.knowledge.parsers.base import DocumentParser
from app.knowledge.parsers.docx import DocxParser
from app.knowledge.parsers.markdown import MarkdownParser
from app.knowledge.parsers.pdf import PDFParser
from app.knowledge.parsers.text import TextParser


class DocumentParserFactory:
    """Resolve a canonical file type to its parser implementation."""

    _PARSERS: dict[str, type[DocumentParser]] = {
        "pdf": PDFParser,
        "docx": DocxParser,
        "txt": TextParser,
        "markdown": MarkdownParser,
    }

    @classmethod
    def create(cls, file_type: str) -> DocumentParser:
        parser = cls._PARSERS.get(file_type)
        if parser is None:
            raise KnowledgeProcessingError(
                "The document type cannot be parsed."
            )

        return parser()
