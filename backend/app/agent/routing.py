from app.agent.state import AgentState


def route_after_input_guard(state: AgentState) -> str:
    """Skip model work when deterministic input validation rejects a message."""
    return "persist" if state.get("input_rejected", False) else "classify"


def route_after_classification(state: AgentState) -> str:
    """Route account-specific requests away from knowledge generation."""
    classification = state.get("classification")
    if classification is None:
        return "persist"

    if classification.needs_account_data:
        return "account_data_guard"

    return "retrieve_knowledge"


def route_after_retrieval(state: AgentState) -> str:
    """Do not invoke an LLM when retrieval produced no usable evidence."""
    return (
        "output_guard"
        if state.get("insufficient_evidence", False)
        else "generate"
    )
