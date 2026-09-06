from collections.abc import Sequence
from dataclasses import dataclass

from app.rag.schemas import RAGRetrievedChunk


@dataclass(frozen=True, slots=True)
class ContextAssembly:
    text: str
    chunks: tuple[RAGRetrievedChunk, ...]


def assemble_context(
    chunks: Sequence[RAGRetrievedChunk],
    *,
    max_characters: int,
) -> ContextAssembly:
    """Format bounded, deterministic evidence blocks for the LLM."""
    if max_characters <= 0:
        return ContextAssembly(text="", chunks=())

    blocks: list[str] = []
    included_chunks: list[RAGRetrievedChunk] = []
    current_length = 0

    for source_index, chunk in enumerate(chunks, start=1):
        header = _format_source_header(source_index, chunk)
        content_prefix = f"{header}\nContent:\n"
        separator = "\n\n" if blocks else ""
        available = max_characters - current_length - len(separator)

        if available <= len(content_prefix):
            break

        complete_block = f"{content_prefix}{chunk.content}"
        if len(complete_block) <= available:
            block = complete_block
        else:
            content_budget = available - len(content_prefix)
            block = (
                f"{content_prefix}{chunk.content[:content_budget]}"
                "\n[Content truncated to fit the context budget.]"
            )

            if len(block) > available:
                block = block[:available]

        blocks.append(block)
        included_chunks.append(chunk)
        current_length += len(separator) + len(block)

        if len(block) < len(complete_block):
            break

    return ContextAssembly(
        text="\n\n".join(blocks),
        chunks=tuple(included_chunks),
    )


def _format_source_header(
    source_index: int,
    chunk: RAGRetrievedChunk,
) -> str:
    lines = [
        f"[SOURCE {source_index}]",
        f"Document: {chunk.document_name}",
        f"Chunk ID: {chunk.chunk_id}",
    ]

    if chunk.page is not None:
        lines.append(f"Page: {chunk.page}")

    if chunk.section:
        lines.append(f"Section: {chunk.section}")

    return "\n".join(lines)
