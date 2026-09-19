"""
Query Router — POST /query endpoint.

Invokes the LangGraph RAG pipeline and returns structured JSON with:
- answer
- citations (with source attribution)
- response_type
- confidence score
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from app.graph.workflow import get_rag_graph
from app.dependencies import get_current_user
from app.services.supabase_service import (
    create_chat_session,
    get_chat_messages,
    add_chat_message,
)

router = APIRouter(tags=["query"])


class QueryRequest(BaseModel):
    """Request body for POST /query."""
    question: str = Field(..., min_length=3, max_length=1000, description="User's legal question")
    doc_id: str = Field(default="", description="Optional: specific document ID to search")
    session_id: str | None = Field(default=None, description="Optional: chat session ID to resume")


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
    session_id: str | None = None


DISCLAIMER = (
    ">> This is general legal information, not legal advice. "
    "Please consult a qualified advocate for your specific situation."
)


@router.post("/query", response_model=QueryResponse)
async def query(
    request: QueryRequest,
    user_id: str = Depends(get_current_user),
):
    """
    RAG query endpoint. Invokes the LangGraph pipeline.

    Flow: route_input -> contextualize_query -> retrieve -> grade -> generate -> check -> format -> response
    """
    session_id = request.session_id
    chat_history = []

    try:
        # Manage Chat Session
        if not session_id:
            title = request.question[:30] + "..." if len(request.question) > 30 else request.question
            session_id = create_chat_session(user_id=user_id, title=title)
        else:
            chat_history = get_chat_messages(session_id=session_id, limit=6)  # Last 3 turns
    except Exception as e:
        print(f"[QUERY] Failed to manage session: {e}")
        # Continue without history if DB fails
        pass

    # Build initial state
    initial_state = {
        "question": request.question,
        "user_id": user_id,
        "doc_id": request.doc_id,
        "session_id": session_id or "",
        "chat_history": chat_history,
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
        result = get_rag_graph().invoke(initial_state)

        # Build response
        response_type = result.get("response_type", "answer")
        answer = result.get("answer", "")
        
        # Save to Chat History
        if session_id:
            try:
                # Save the new exchange
                add_chat_message(session_id=session_id, role="user", content=request.question)
                add_chat_message(session_id=session_id, role="assistant", content=answer)
            except Exception as e:
                print(f"[QUERY] Failed to save chat messages: {e}")

        disclaimer = DISCLAIMER if response_type == "answer" else None

        return QueryResponse(
            answer=answer,
            response_type=response_type,
            citations=[Citation(**c) for c in result.get("citations", [])],
            confidence=result.get("confidence", 0.0),
            disclaimer=disclaimer,
            session_id=session_id,
        )

    except Exception as e:
        print(f"[QUERY] Pipeline error: {e}")
        raise HTTPException(status_code=500, detail=f"RAG pipeline error: {str(e)[:200]}")
