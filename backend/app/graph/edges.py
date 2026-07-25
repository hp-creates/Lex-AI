"""
LangGraph Conditional Edges — routing logic between nodes.

These functions decide which node to execute next based on the current state.
"""

from app.graph.state import RAGState


def route_after_input(state: RAGState) -> str:
    """After route_input: reject off-topic or proceed to retrieval."""
    if state.get("response_type") == "rejection":
        return "reject"
    return "retrieve"


def route_after_grading(state: RAGState) -> str:
    """
    After grade_docs:
    - If relevant docs found -> generate answer
    - If no relevant docs and retries left -> rewrite query
    - If no relevant docs and max retries -> format as no_context
    """
    relevant = state.get("relevant_docs", [])
    attempts = state.get("retrieval_attempts", 0)

    if len(relevant) > 0:
        return "generate"

    if attempts < 2:
        return "rewrite_query"

    # Max retries exhausted — no relevant context
    return "format_response"


def route_after_hallucination_check(state: RAGState) -> str:
    """
    After check_hallucination:
    - If grounded -> format response
    - If hallucinated and retry available -> regenerate
    - If hallucinated and max retries -> format anyway (with warning)
    """
    is_hallucinated = state.get("is_hallucinated", False)
    attempts = state.get("generation_attempts", 0)

    if not is_hallucinated:
        return "format_response"

    if attempts < 2:
        return "generate"  # Retry once

    # Max retries — return what we have
    return "format_response"
