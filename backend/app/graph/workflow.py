"""
LangGraph Workflow — wires nodes + edges into a compiled StateGraph.

This is the compiled RAG pipeline. Call `rag_graph.invoke(state)` to run.
"""

from langgraph.graph import StateGraph, END

from app.graph.state import RAGState
from app.graph.nodes import (
    route_input,
    contextualize_query,
    retrieve,
    grade_docs,
    rewrite_query,
    generate,
    check_hallucination,
    format_response,
    reject,
    web_search,
)
from app.graph.edges import (
    route_after_input,
    route_after_grading,
    route_after_hallucination_check,
    route_after_web_search,
)


def build_rag_graph():
    """
    Build and compile the LangGraph RAG workflow.
    Services (embedder, vector_store, BM25) are initialized by main.py lifespan
    before this is called — do NOT re-initialize them here.
    """

    """
    Flow:
    route_input -> [reject | contextualize_query]
    contextualize_query -> retrieve
    retrieve -> grade_docs
    grade_docs -> [generate | rewrite_query | web_search]
    rewrite_query -> retrieve (loop)
    web_search -> [generate | format_response]
    generate -> check_hallucination
    check_hallucination -> format_response
    format_response -> END
    reject -> END
    """
    graph = StateGraph(RAGState)

    # Add all nodes
    graph.add_node("route_input", route_input)
    graph.add_node("contextualize_query", contextualize_query)
    graph.add_node("retrieve", retrieve)
    graph.add_node("grade_docs", grade_docs)
    graph.add_node("rewrite_query", rewrite_query)
    graph.add_node("generate", generate)
    graph.add_node("check_hallucination", check_hallucination)
    graph.add_node("format_response", format_response)
    graph.add_node("reject", reject)
    graph.add_node("web_search", web_search)

    # Set entry point
    graph.set_entry_point("route_input")

    # Conditional edges
    graph.add_conditional_edges(
        "route_input",
        route_after_input,
        {"reject": "reject", "contextualize_query": "contextualize_query"},
    )

    graph.add_edge("contextualize_query", "retrieve")
    graph.add_edge("retrieve", "grade_docs")

    graph.add_conditional_edges(
        "grade_docs",
        route_after_grading,
        {"generate": "generate", "rewrite_query": "rewrite_query", "web_search": "web_search"},
    )

    graph.add_edge("rewrite_query", "retrieve")

    # Web search fallback — route to generate if results found, else no_context
    graph.add_conditional_edges(
        "web_search",
        route_after_web_search,
        {"generate": "generate", "format_response": "format_response"},
    )

    graph.add_edge("generate", "check_hallucination")

    # No retry loop — always proceed to format_response
    graph.add_edge("check_hallucination", "format_response")

    # Terminal edges
    graph.add_edge("format_response", END)
    graph.add_edge("reject", END)

    return graph.compile()


# Built lazily on first use so module import doesn't trigger service initialization
_rag_graph = None


def get_rag_graph():
    """Return the compiled graph, building it on first call."""
    global _rag_graph
    if _rag_graph is None:
        _rag_graph = build_rag_graph()
    return _rag_graph
