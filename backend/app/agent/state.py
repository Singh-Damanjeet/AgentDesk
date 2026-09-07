from typing import TypedDict

from app.rag.schemas import RAGRetrievedChunk
from app.schemas.agent import ClassificationResult


class ConversationContextItem(TypedDict):
    """A bounded, redacted conversation item available to the classifier."""

    sender_type: str
    content: str


class AgentState(TypedDict, total=False):
    """Serializable workflow state.

    Database sessions, provider clients, credentials, and ORM objects are
    intentionally excluded. They remain owned by the service that executes
    the graph.
    """

    trace_id: str
    ticket_id: str
    session_id: str
    user_message: str
    conversation_context: list[ConversationContextItem]
    company_context: dict[str, str]
    classification: ClassificationResult | None
    retrieved_chunks: list[RAGRetrievedChunk]
    answer: str | None
    insufficient_evidence: bool
    requires_human_review: bool
    input_rejected: bool
    classifier_failed: bool
    guard_reason: str | None
    retrieval_reason: str | None
    persisted: bool
    error: str | None


SupportAgentState = AgentState
