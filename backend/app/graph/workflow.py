"""
LangGraph Workflow — wires nodes + edges into a compiled StateGraph.

This is the compiled RAG pipeline. Call `rag_graph.invoke(state)` to run.
"""

from langgraph.graph import StateGraph, END

from app.graph.state import RAGState
from app.graph.nodes import (
    route_input,
    retrieve,
    grade_docs,
    rewrite_query,
    generate,
    check_hallucination,
    format_response,
    reject,
)
from app.graph.edges import (
    route_after_input,
    route_after_grading,
    route_after_hallucination_check,
)


def build_rag_graph():
    """
    Build and compile the LangGraph RAG workflow.

    Flow:
    route_input -> [reject | retrieve]
    retrieve -> grade_docs
    grade_docs -> [generate | rewrite_query | format_response]
    rewrite_query -> retrieve (loop)
    generate -> check_hallucination
    check_hallucination -> [format_response | generate (retry)]
    format_response -> END
    reject -> END
    """
    graph = StateGraph(RAGState)

    # Add all nodes
    graph.add_node("route_input", route_input)
    graph.add_node("retrieve", retrieve)
    graph.add_node("grade_docs", grade_docs)
    graph.add_node("rewrite_query", rewrite_query)
    graph.add_node("generate", generate)
    graph.add_node("check_hallucination", check_hallucination)
    graph.add_node("format_response", format_response)
    graph.add_node("reject", reject)

    # Set entry point
    graph.set_entry_point("route_input")

    # Conditional edges
    graph.add_conditional_edges(
        "route_input",
        route_after_input,
        {"reject": "reject", "retrieve": "retrieve"},
    )

    graph.add_edge("retrieve", "grade_docs")

    graph.add_conditional_edges(
        "grade_docs",
        route_after_grading,
        {"generate": "generate", "rewrite_query": "rewrite_query", "format_response": "format_response"},
    )

    graph.add_edge("rewrite_query", "retrieve")

    graph.add_edge("generate", "check_hallucination")

    graph.add_conditional_edges(
        "check_hallucination",
        route_after_hallucination_check,
        {"format_response": "format_response", "generate": "generate"},
    )

    # Terminal edges
    graph.add_edge("format_response", END)
    graph.add_edge("reject", END)

    return graph.compile()


# Global compiled graph -- initialized once at startup
rag_graph = build_rag_graph()
