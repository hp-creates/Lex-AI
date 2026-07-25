"""
LangGraph State Definition — shared state across all RAG workflow nodes.

This TypedDict defines every field that flows through the LangGraph pipeline.
Each node reads and writes to specific fields.
"""

from typing import TypedDict


class RAGState(TypedDict):
    """Shared state for the LangGraph RAG workflow."""

    # === Input (set by the router) ===
    question: str                      # Original user question
    user_id: str                       # Supabase user UUID
    doc_id: str                        # Optional: specific doc to search

    # === Retrieval ===
    query_to_search: str               # May be rewritten by rewrite_query node
    retrieved_docs: list[dict]         # Raw chunks from hybrid search
    retrieval_attempts: int            # Counter for retry logic (max 2)

    # === Grading ===
    relevant_docs: list[dict]          # Docs that passed relevance grading

    # === Generation ===
    answer: str                        # LLM-generated answer
    generation_attempts: int           # Counter for hallucination retry (max 1)
    is_hallucinated: bool              # Result of hallucination check

    # === Output ===
    citations: list[dict]              # Source attribution per chunk used
    confidence: float                  # Top RRF/similarity score
    response_type: str                 # "answer" | "rejection" | "no_context"
