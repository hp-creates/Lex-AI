"""
LangGraph Nodes — each node is a function that takes RAGState and returns a partial update.

Nodes:
1. route_input     - Classify: legal question or off-topic?
2. retrieve        - Run hybrid search (vector + BM25 -> RRF)
3. grade_docs      - LLM grades each chunk for relevance
4. rewrite_query   - LLM rewrites query for better retrieval
5. generate        - Build prompt + call Groq LLaMA 3.3
6. check_hallucination - LLM checks if answer is grounded in sources
7. format_response - Attach citations, disclaimer, confidence
8. reject          - Return polite off-topic rejection
"""

from langchain_groq import ChatGroq

from app.config import settings
from app.graph.state import RAGState
from app.prompts.system_prompt import (
    SYSTEM_PROMPT,
    GRADING_PROMPT,
    REWRITE_PROMPT,
    HALLUCINATION_CHECK_PROMPT,
)
from app.services.hybrid_retriever import hybrid_search


def _get_llm() -> ChatGroq:
    """Get the Groq LLM instance."""
    return ChatGroq(
        api_key=settings.GROQ_API_KEY,
        model=settings.GROQ_MODEL,
        temperature=0,
        max_tokens=2048,
    )


# --- Off-topic keywords that signal a non-legal question ---
_OFF_TOPIC_KEYWORDS = [
    "recipe", "cook", "weather", "movie", "song", "poem", "joke",
    "game", "sport", "cricket", "football", "dating", "relationship",
    "homework", "math", "science", "code", "programming", "python",
    "write me", "tell me a story", "generate", "create an image",
]


def route_input(state: RAGState) -> dict:
    """
    Node 1: Classify the question.
    - If off-topic -> set response_type = "rejection"
    - If legal -> set query_to_search = question
    """
    question = state["question"].lower().strip()

    # Quick keyword check for obviously off-topic queries
    is_off_topic = any(kw in question for kw in _OFF_TOPIC_KEYWORDS)

    if is_off_topic:
        return {
            "response_type": "rejection",
            "query_to_search": "",
            "retrieval_attempts": 0,
            "generation_attempts": 0,
        }

    return {
        "response_type": "",  # Will be set later
        "query_to_search": state["question"],
        "retrieval_attempts": 0,
        "generation_attempts": 0,
        "retrieved_docs": [],
        "relevant_docs": [],
        "citations": [],
    }


def retrieve(state: RAGState) -> dict:
    """
    Node 2: Run hybrid search (vector + BM25 -> RRF).
    Searches both law corpus and user documents.
    """
    query = state["query_to_search"]
    user_id = state.get("user_id", "")
    doc_id = state.get("doc_id", "")

    results = hybrid_search(
        query=query,
        user_id=user_id if user_id else None,
        doc_id=doc_id if doc_id else None,
        top_k=5,
    )

    return {
        "retrieved_docs": results,
        "retrieval_attempts": state.get("retrieval_attempts", 0) + 1,
    }


def grade_docs(state: RAGState) -> dict:
    """
    Node 3: LLM grades each retrieved chunk for relevance.
    Only chunks graded "yes" pass to the generation step.
    """
    llm = _get_llm()
    question = state["question"]
    docs = state.get("retrieved_docs", [])

    if not docs:
        return {"relevant_docs": []}

    relevant = []
    for doc in docs:
        prompt = GRADING_PROMPT.format(
            question=question,
            document=doc.get("text", "")[:500],  # Truncate for grading
        )

        try:
            response = llm.invoke(prompt)
            grade = response.content.strip().lower()

            if "yes" in grade:
                relevant.append(doc)
        except Exception as e:
            print(f"[GRADE] Error grading doc: {e}")
            # On error, include the doc (fail-open)
            relevant.append(doc)

    return {"relevant_docs": relevant}


def rewrite_query(state: RAGState) -> dict:
    """
    Node 4: LLM rewrites the query for better retrieval.
    Called when grade_docs finds zero relevant documents.
    """
    llm = _get_llm()
    question = state["question"]

    prompt = REWRITE_PROMPT.format(question=question)

    try:
        response = llm.invoke(prompt)
        rewritten = response.content.strip()
        print(f"[REWRITE] '{question}' -> '{rewritten}'")
        return {"query_to_search": rewritten}
    except Exception as e:
        print(f"[REWRITE] Error: {e}")
        return {"query_to_search": question}  # Keep original on failure


def generate(state: RAGState) -> dict:
    """
    Node 5: Build prompt with context + system instructions, call Groq LLaMA.
    """
    llm = _get_llm()
    question = state["question"]
    relevant_docs = state.get("relevant_docs", [])

    if not relevant_docs:
        return {
            "answer": "I could not find relevant information in the available legal documents. Please rephrase your question or consult a qualified advocate.",
            "response_type": "no_context",
            "generation_attempts": state.get("generation_attempts", 0) + 1,
        }

    # Build context from relevant docs
    context_parts = []
    for i, doc in enumerate(relevant_docs):
        source = doc.get("source", "Unknown")
        section = doc.get("section", "Unknown")
        text = doc.get("text", "")
        context_parts.append(f"[Document {i+1}] Source: {source} | {section}\n{text}")

    context = "\n\n---\n\n".join(context_parts)

    # Build the user message with context + question
    user_message = f"""## Context Documents (use ONLY these to answer)

{context}

---

## User Question

{question}"""

    try:
        from langchain_core.messages import SystemMessage, HumanMessage

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_message),
        ]

        response = llm.invoke(messages)
        answer = response.content.strip()

        return {
            "answer": answer,
            "generation_attempts": state.get("generation_attempts", 0) + 1,
        }
    except Exception as e:
        print(f"[GENERATE] Error: {e}")
        return {
            "answer": f"An error occurred while generating the response: {str(e)[:100]}",
            "response_type": "no_context",
            "generation_attempts": state.get("generation_attempts", 0) + 1,
        }


def check_hallucination(state: RAGState) -> dict:
    """
    Node 6: LLM checks if the answer is grounded in the source documents.
    """
    llm = _get_llm()
    answer = state.get("answer", "")
    relevant_docs = state.get("relevant_docs", [])

    if not relevant_docs or not answer:
        return {"is_hallucinated": False}

    # Build source text for checking
    source_text = "\n\n".join([
        f"[{doc.get('source', '')} | {doc.get('section', '')}]: {doc.get('text', '')[:300]}"
        for doc in relevant_docs
    ])

    prompt = HALLUCINATION_CHECK_PROMPT.format(
        documents=source_text,
        answer=answer[:1000],  # Truncate for efficiency
    )

    try:
        response = llm.invoke(prompt)
        verdict = response.content.strip().lower()
        is_hallucinated = "hallucinated" in verdict

        if is_hallucinated:
            print(f"[HALLUCINATION] Detected! Will retry generation.")

        return {"is_hallucinated": is_hallucinated}
    except Exception as e:
        print(f"[HALLUCINATION] Check error: {e}")
        return {"is_hallucinated": False}  # Fail-open


def format_response(state: RAGState) -> dict:
    """
    Node 7: Attach citations, confidence scores, and disclaimer.
    """
    relevant_docs = state.get("relevant_docs", [])
    answer = state.get("answer", "")
    response_type = state.get("response_type", "")

    # If no relevant docs were found after retries
    if not relevant_docs and response_type != "rejection":
        return {
            "response_type": "no_context",
            "citations": [],
            "confidence": 0.0,
        }

    # Build citations from relevant docs
    citations = []
    for doc in relevant_docs:
        citations.append({
            "source": doc.get("source", ""),
            "act_short": doc.get("act_short", ""),
            "section": doc.get("section", ""),
            "section_title": doc.get("section_title", ""),
            "text": doc.get("text", "")[:300],  # Truncate for response
            "confidence": round(doc.get("rrf_score", doc.get("score", 0)), 4),
            "search_type": doc.get("search_type", "hybrid"),
        })

    # Get top confidence score
    top_confidence = max(
        (doc.get("rrf_score", doc.get("score", 0)) for doc in relevant_docs),
        default=0.0,
    )

    return {
        "response_type": response_type or "answer",
        "citations": citations,
        "confidence": round(top_confidence, 4),
    }


def reject(state: RAGState) -> dict:
    """
    Node 8: Return polite off-topic rejection.
    """
    return {
        "answer": "I can only assist with questions about Indian law and citizen rights. "
                  "Please ask about your legal rights, laws, or uploaded legal documents.",
        "response_type": "rejection",
        "citations": [],
        "confidence": 0.0,
    }
