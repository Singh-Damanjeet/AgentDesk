import re
from pathlib import Path

from app.knowledge.errors import KnowledgeProcessingError
from app.knowledge.parsers.base import ParsedSection


HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


class MarkdownParser:
    def parse(self, source_path: Path) -> list[ParsedSection]:
        try:
            content = source_path.read_bytes().decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise KnowledgeProcessingError(
                "Unable to decode this Markdown document as UTF-8."
            ) from exc
        except OSError as exc:
            raise KnowledgeProcessingError(
                "The Markdown document could not be read."
            ) from exc

        if not content.strip():
            raise KnowledgeProcessingError(
                "The Markdown document does not contain readable content."
            )

        sections: list[ParsedSection] = []
        current_heading: str | None = None
        paragraph_lines: list[str] = []

        def flush_paragraph() -> None:
            if not paragraph_lines:
                return

            paragraph = "\n".join(paragraph_lines).strip()
            paragraph_lines.clear()

            if paragraph:
                sections.append(
                    ParsedSection(
                        text=paragraph,
                        section=current_heading,
                    )
                )

        for line in content.replace("\r\n", "\n").replace("\r", "\n").split(
            "\n"
        ):
            heading_match = HEADING_PATTERN.match(line.strip())

            if heading_match:
                flush_paragraph()
                current_heading = heading_match.group(2).rstrip("#").strip()
                if not current_heading:
                    continue

                sections.append(
                    ParsedSection(
                        text=current_heading,
                        section=current_heading,
                        metadata={
                            "kind": "heading",
                            "heading_level": str(len(heading_match.group(1))),
                        },
                    )
                )
            elif line.strip():
                paragraph_lines.append(line)
            else:
                flush_paragraph()

        flush_paragraph()

        if not sections:
            raise KnowledgeProcessingError(
                "The Markdown document does not contain readable content."
            )

        return sections
