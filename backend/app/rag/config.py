from dataclasses import dataclass
import math


DEFAULT_TOP_K = 5
# This is an initial conservative value, intended to be tuned with retrieval
# evaluation rather than treated as a universal relevance boundary.
DEFAULT_MIN_RELEVANCE_SCORE = 0.35
DEFAULT_MAX_CONTEXT_CHARACTERS = 12_000
MAX_QUESTION_LENGTH = 2_000
INSUFFICIENT_EVIDENCE_ANSWER = (
    "I don't have enough information in the configured knowledge base "
    "to answer that reliably."
)


@dataclass(frozen=True, slots=True)
class RAGConfig:
    """Centralized controls for the first grounded retrieval pipeline."""

    top_k: int = DEFAULT_TOP_K
    min_relevance_score: float = DEFAULT_MIN_RELEVANCE_SCORE
    max_context_characters: int = DEFAULT_MAX_CONTEXT_CHARACTERS

    def __post_init__(self) -> None:
        if self.top_k <= 0:
            raise ValueError("RAG top_k must be greater than zero.")

        if not math.isfinite(self.min_relevance_score):
            raise ValueError("RAG relevance score must be finite.")

        if not -1.0 <= self.min_relevance_score <= 1.0:
            raise ValueError(
                "RAG relevance score must be between -1 and 1."
            )

        if self.max_context_characters <= 0:
            raise ValueError(
                "RAG context budget must be greater than zero."
            )


DEFAULT_RAG_CONFIG = RAGConfig()
