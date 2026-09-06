import re
from dataclasses import dataclass

from app.knowledge.config import ChunkSettings, DEFAULT_CHUNK_SETTINGS
from app.knowledge.parsers.base import ParsedSection


@dataclass(frozen=True, slots=True)
class TextChunk:
    text: str
    page: int | None
    section: str | None
    token_count: int
    char_start: int
    char_end: int
    metadata: dict[str, str]


class TextChunker:
    """Create deterministic approximate-token chunks with bounded overlap."""

    def __init__(self, settings: ChunkSettings = DEFAULT_CHUNK_SETTINGS):
        self.settings = settings

    def chunk(self, sections: list[ParsedSection]) -> list[TextChunk]:
        merged_sections = self._merge_adjacent_sections(sections)
        chunks: list[TextChunk] = []

        for section in merged_sections:
            chunks.extend(self._chunk_section(section))

        return chunks

    @staticmethod
    def _merge_adjacent_sections(
        sections: list[ParsedSection],
    ) -> list[ParsedSection]:
        merged: list[ParsedSection] = []

        for section in sections:
            if (
                merged
                and merged[-1].page == section.page
                and merged[-1].section == section.section
            ):
                previous = merged[-1]
                merged[-1] = previous.model_copy(
                    update={
                        "text": f"{previous.text}\n\n{section.text}",
                        "metadata": {
                            **previous.metadata,
                            **section.metadata,
                        },
                    }
                )
            else:
                merged.append(section)

        return merged

    def _chunk_section(self, section: ParsedSection) -> list[TextChunk]:
        token_spans = list(re.finditer(r"\S+", section.text))
        if not token_spans:
            return []

        chunks: list[TextChunk] = []
        start_token = 0

        while start_token < len(token_spans):
            end_token = min(
                start_token + self.settings.target_tokens,
                len(token_spans),
            )
            start_char = token_spans[start_token].start()
            end_char = token_spans[end_token - 1].end()
            chunk_text = section.text[start_char:end_char].strip()

            chunks.append(
                TextChunk(
                    text=chunk_text,
                    page=section.page,
                    section=section.section,
                    token_count=end_token - start_token,
                    char_start=start_char,
                    char_end=end_char,
                    metadata=dict(section.metadata),
                )
            )

            if end_token == len(token_spans):
                break

            start_token = max(
                end_token - self.settings.overlap_tokens,
                start_token + 1,
            )

        return chunks
