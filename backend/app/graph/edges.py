"""
LangGraph Conditional Edges — routing logic between nodes.

These functions decide which node to execute next based on the current state.
"""

from app.graph.state import RAGState


def route_after_input(state: RAGState) -> str:
    """After route_input: reject off-topic or proceed to retrieval."""
    if state.get("response_type") == "rejection":
        return "reject"
    return "contextualize_query"


def route_after_grading(state: RAGState) -> str:
    """
    After grade_docs:
    - If relevant docs found -> generate answer
    - If no relevant docs and retries left -> rewrite query
    - If no relevant docs and max retries -> try web search
    """
    relevant = state.get("relevant_docs", [])
    attempts = state.get("retrieval_attempts", 0)

    if len(relevant) > 0:
        return "generate"

    if attempts < 2:
        return "rewrite_query"

    # Max retries exhausted — try web search as last resort
    return "web_search"


def route_after_hallucination_check(state: RAGState) -> str:
    """
    After check_hallucination:
    - Always proceed to format_response (no retry loop).
    - If hallucinated, format_response will append a warning.
    """
    is_hallucinated = state.get("is_hallucinated", False)

    if is_hallucinated:
        print("[EDGE] Hallucination detected — proceeding with warning, no retry.")

    return "format_response"


def route_after_web_search(state: RAGState) -> str:
    """
    After web_search:
    - If web results found relevant docs -> generate answer
    - If no results -> format as no_context
    """
    relevant = state.get("relevant_docs", [])

    if len(relevant) > 0:
        return "generate"

    return "format_response"

