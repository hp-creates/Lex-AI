"""
Query Router — POST /query endpoint.

Invokes the LangGraph RAG pipeline and returns structured JSON with:
- answer
- citations (with source attribution)
- response_type
- confidence score
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.graph.workflow import rag_graph

router = APIRouter(tags=["query"])


class QueryRequest(BaseModel):
    """Request body for POST /query."""
    question: str = Field(..., min_length=3, max_length=1000, description="User's legal question")
    doc_id: str = Field(default="", description="Optional: specific document ID to search")


class Citation(BaseModel):
    """A single source citation."""
    source: str = ""
    act_short: str = ""
    section: str = ""
    section_title: str = ""
    text: str = ""
    confidence: float = 0.0
    search_type: str = "hybrid"


class QueryResponse(BaseModel):
    """Response body for POST /query."""
    answer: str
    response_type: str  # "answer" | "rejection" | "no_context"
    citations: list[Citation] = []
    confidence: float = 0.0
    disclaimer: str | None = None


DISCLAIMER = (
    ">> This is general legal information, not legal advice. "
    "Please consult a qualified advocate for your specific situation."
)


@router.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """
    RAG query endpoint. Invokes the LangGraph pipeline.

    Flow: route_input -> retrieve -> grade -> generate -> check -> format -> response
    """
    # Build initial state
    initial_state = {
        "question": request.question,
        "user_id": "",  # TODO: extract from JWT in auth middleware
        "doc_id": request.doc_id,
        "query_to_search": "",
        "retrieved_docs": [],
        "retrieval_attempts": 0,
        "relevant_docs": [],
        "answer": "",
        "generation_attempts": 0,
        "is_hallucinated": False,
        "citations": [],
        "confidence": 0.0,
        "response_type": "",
    }

    try:
        # Run the LangGraph pipeline
        result = rag_graph.invoke(initial_state)

        # Build response
        response_type = result.get("response_type", "answer")
        disclaimer = DISCLAIMER if response_type == "answer" else None

        return QueryResponse(
            answer=result.get("answer", ""),
            response_type=response_type,
            citations=[Citation(**c) for c in result.get("citations", [])],
            confidence=result.get("confidence", 0.0),
            disclaimer=disclaimer,
        )

    except Exception as e:
        print(f"[QUERY] Pipeline error: {e}")
        raise HTTPException(status_code=500, detail=f"RAG pipeline error: {str(e)[:200]}")
