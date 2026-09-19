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
9. web_search      - Tavily fallback when corpus has no relevant docs
"""

import re

from langchain_groq import ChatGroq

from app.config import settings
from app.graph.state import RAGState
from app.prompts.system_prompt import (
    SYSTEM_PROMPT,
    GRADING_PROMPT,
    REWRITE_PROMPT,
    HALLUCINATION_CHECK_PROMPT,
    CONTEXTUALIZE_PROMPT,
)
from app.services.hybrid_retriever import hybrid_search
from app.services.web_search import tavily_search


def _strip_think(text: str) -> str:
    """Strip <think>...</think> reasoning blocks from model outputs."""
    return re.sub(r"<think>[\s\S]*?</think>", "", text).strip()


def _extract_content(response) -> str:
    """
    Extract text content from an LLM response.

    Handles two response styles:
    - Standard chat models (e.g. llama-*): content is in response.content
    - Reasoning/GPT-OSS models (e.g. openai/gpt-oss-20b): the final answer
      is in response.content; reasoning trace is in additional_kwargs['reasoning_content'].
      However if content is empty, fall back to reasoning_content so we
      always return something useful.
    """
    content = response.content or ""
    if not content.strip():
        # Reasoning model returned empty content — try additional_kwargs
        ak = getattr(response, "additional_kwargs", {}) or {}
        content = (
            ak.get("reasoning_content")
            or ak.get("content")
            or ""
        )
    return _strip_think(content)


def _extract_verdict(response, positive_keyword: str = "yes") -> bool:
    """
    Extract a binary yes/no verdict from a reasoning model response.

    Unlike _extract_content (which may fall back to the full reasoning trace),
    this function checks response.content FIRST (the final answer field) and
    only falls back to the LAST word of reasoning_content.

    This prevents false matches like the reasoning trace containing
    "the document is not relevant" being matched by `'yes' in text`.
    """
    # 1. Check response.content first — this is the final answer for reasoning models
    content = (response.content or "").strip()
    content = _strip_think(content)
    if content:
        # Take only the last line/word to avoid matching stray occurrences
        last_line = content.strip().splitlines()[-1].strip().lower()
        return positive_keyword in last_line

    # 2. Fallback: check reasoning_content, but only the LAST line
    ak = getattr(response, "additional_kwargs", {}) or {}
    reasoning = ak.get("reasoning_content", "").strip()
    if reasoning:
        last_line = reasoning.strip().splitlines()[-1].strip().lower()
        return positive_keyword in last_line

    # 3. No content at all — fail-open (assume relevant)
    return True


def _get_llm() -> ChatGroq:
    """Get the Groq LLM instance."""
    return ChatGroq(
        api_key=settings.GROQ_API_KEY,
        model=settings.GROQ_MODEL,
        temperature=0,
        max_tokens=4096,  # Raised from 2048 — prevents cut-off responses
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


def contextualize_query(state: RAGState) -> dict:
    """
    Node 1.5: If chat history exists, rewrite the query to be standalone.
    Example: "what are the charges?" -> "what are the charges mentioned in FIR 0184?"
    """
    history = state.get("chat_history", [])
    question = state["question"]

    if not history:
        # No history, no need to contextualize
        return {"query_to_search": question}

    llm = _get_llm()
    
    # Format history as a readable string
    history_str = ""
    for msg in history:
        role = "User" if msg.get("role") == "user" else "Assistant"
        history_str += f"{role}: {msg.get('content')}\n"

    prompt = CONTEXTUALIZE_PROMPT.format(
        chat_history=history_str.strip(),
        question=question
    )

    try:
        response = llm.invoke(prompt)
        standalone_query = _extract_content(response)
        print(f"[CONTEXTUALIZE] '{question}' -> '{standalone_query}'")
        return {"query_to_search": standalone_query}
    except Exception as e:
        print(f"[CONTEXTUALIZE] Error: {e}")
        return {"query_to_search": question}


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
        top_k=6,  # Raised from 3 — senior review: top_k=3 likely cuts off relevant chunks
    )

    return {
        "retrieved_docs": results,
        "retrieval_attempts": state.get("retrieval_attempts", 0) + 1,
    }


def grade_docs(state: RAGState) -> dict:
    """
    Node 3: LLM grades each retrieved chunk for relevance.
    Only chunks graded "yes" pass to the generation step.
    Uses ThreadPoolExecutor to grade all chunks in PARALLEL (~1.5s vs ~7s sequential).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    llm = _get_llm()
    question = state["question"]
    docs = state.get("retrieved_docs", [])

    if not docs:
        return {"relevant_docs": []}

    def _grade_single(doc: dict) -> tuple[dict, bool]:
        """Grade a single doc chunk. Returns (doc, is_relevant)."""
        # Include metadata in grading context so the LLM can see source/section info
        source = doc.get("source", "Unknown")
        section = doc.get("section", "")
        section_title = doc.get("section_title", "")
        meta_header = f"[Source: {source}"
        if section:
            meta_header += f" | Section: {section}"
        if section_title:
            meta_header += f" | Title: {section_title}"
        meta_header += "]\n"

        doc_text = meta_header + doc.get("text", "")[:600]
        prompt = GRADING_PROMPT.format(
            question=question,
            document=doc_text,
        )
        try:
            response = llm.invoke(prompt)
            is_relevant = _extract_verdict(response, "yes")
            print(f"[GRADE] {'PASS' if is_relevant else 'FAIL'}: {source} {section} — raw='{(response.content or '')[:80]}'")
            return (doc, is_relevant)
        except Exception as e:
            print(f"[GRADE] Error grading doc: {e}")
            return (doc, True)  # Fail-open: include on error

    # Run all grading calls in parallel
    relevant = []
    with ThreadPoolExecutor(max_workers=len(docs)) as executor:
        futures = {executor.submit(_grade_single, doc): doc for doc in docs}
        for future in as_completed(futures):
            doc, is_relevant = future.result()
            if is_relevant:
                relevant.append(doc)

    print(f"[GRADE] {len(relevant)}/{len(docs)} chunks passed relevance grading")
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
        rewritten = _extract_content(response)
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
        context_parts.append(f"[{source} | {section}]\n{text}")

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
        answer = _extract_content(response)

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

    # Build source text for checking — use enough text to avoid false positives
    source_text = "\n\n".join([
        f"[{doc.get('source', '')} | {doc.get('section', '')}]: {doc.get('text', '')[:800]}"
        for doc in relevant_docs
    ])

    prompt = HALLUCINATION_CHECK_PROMPT.format(
        documents=source_text,
        answer=answer[:1000],  # Truncate for efficiency
    )

    try:
        response = llm.invoke(prompt)
        is_hallucinated = _extract_verdict(response, "hallucinated")

        if is_hallucinated:
            print(f"[HALLUCINATION] Detected! Appending warning (no retry).")
        else:
            print(f"[HALLUCINATION] Clean — answer is grounded.")

        return {"is_hallucinated": is_hallucinated}
    except Exception as e:
        print(f"[HALLUCINATION] Check error: {e}")
        return {"is_hallucinated": False}  # Fail-open


def format_response(state: RAGState) -> dict:
    """
    Node 7: Attach citations, confidence scores, and disclaimer.
    If hallucination was detected, append a warning to the answer.
    """
    relevant_docs = state.get("relevant_docs", [])
    answer = state.get("answer", "")
    response_type = state.get("response_type", "")
    is_hallucinated = state.get("is_hallucinated", False)

    # If no relevant docs were found after retries
    if not relevant_docs and response_type != "rejection":
        return {
            "response_type": "no_context",
            "citations": [],
            "confidence": 0.0,
        }

    # Append hallucination warning if detected
    if is_hallucinated and answer:
        answer += (
            "\n\n> ⚠️ **Verification Notice:** Our automated systems detected that "
            "parts of this answer might not be fully backed by the source documents. "
            "Please cross-check with a qualified legal professional."
        )

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
        "answer": answer,
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


def web_search(state: RAGState) -> dict:
    """
    Node 9: Tavily web search fallback.
    Fires only when corpus retrieval + rewrite yield zero relevant docs.
    Results are placed into relevant_docs so the generate node can use them.
    """
    question = state["question"]
    query = state.get("query_to_search", question)

    results = tavily_search(query=query, max_results=3)

    if not results:
        print("[WEB SEARCH] No results — proceeding to format_response")
        return {"web_search_used": True}

    print(f"[WEB SEARCH] Found {len(results)} web results — sending to generate")
    return {
        "relevant_docs": results,
        "web_search_used": True,
    }
