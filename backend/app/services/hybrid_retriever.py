"""
Hybrid Retriever — combines Vector (Qdrant) + BM25 search via Reciprocal Rank Fusion.

Pipeline:
1. Embed query -> vector search (Qdrant) -> semantic matches
2. Tokenize query -> BM25 search -> keyword/exact matches
3. Section metadata lookup -> exact section match by metadata
4. Reciprocal Rank Fusion (RRF) merges all three, docs good in multiple rise to top

Why hybrid?
- Vector search catches meaning ("right to defend" -> Section 96)
- BM25 catches exact terms ("Section 302 IPC" -> exact match)
- Section lookup catches exact section+act by metadata (bypasses chunking issues)
- RRF ensures docs ranked well in BOTH searches are prioritized

k = 5 (RRF constant). Higher k = more uniform weight across ranks.
"""

import re

from app.services.vector_store import vector_store
from app.services.bm25_search import bm25_index
from app.services.embedder import embedder
from app.config import settings


# Map of common abbreviations/aliases -> canonical source names in the corpus
_ACT_ALIASES = {
    "ipc": "Indian Penal Code, 1860",
    "indian penal code": "Indian Penal Code, 1860",
    "crpc": "Code of Criminal Procedure, 1973",
    "code of criminal procedure": "Code of Criminal Procedure, 1973",
    "cpa": "Consumer Protection Act, 2019",
    "consumer protection act": "Consumer Protection Act, 2019",
    "bnss": "Bharatiya Nagarik Suraksha Sanhita, 2023",
    "bharatiya nagarik suraksha sanhita": "Bharatiya Nagarik Suraksha Sanhita, 2023",
    "bns": "Bharatiya Nyaya Sanhita, 2023",
    "bharatiya nyaya sanhita": "Bharatiya Nyaya Sanhita, 2023",
    "it act": "Information Technology Act, 2000",
    "information technology act": "Information Technology Act, 2000",
    "rti": "Right to Information Act, 2005",
    "rti act": "Right to Information Act, 2005",
    "right to information act": "Right to Information Act, 2005",
    "constitution": "Constitution of India",
    "constitution of india": "Constitution of India",
    "pocso": "Protection of Children from Sexual Offences Act, 2012",
    "motor vehicles act": "Motor Vehicles Act, 1988",
    "mv act": "Motor Vehicles Act, 1988",
    "domestic violence act": "Protection of Women from Domestic Violence Act, 2005",
    "dv act": "Protection of Women from Domestic Violence Act, 2005",
    "bsa": "Bharatiya Sakshya Adhiniyam, 2023",
    "bharatiya sakshya adhiniyam": "Bharatiya Sakshya Adhiniyam, 2023",
    "indian evidence act": "Bharatiya Sakshya Adhiniyam, 2023",
    "dpdpa": "Digital Personal Data Protection Act, 2023",
    "data protection act": "Digital Personal Data Protection Act, 2023",
    "digital personal data protection": "Digital Personal Data Protection Act, 2023",
    "hma": "Hindu Marriage Act, 1955",
    "hindu marriage act": "Hindu Marriage Act, 1955",
    "posh": "Sexual Harassment of Women at Workplace Act, 2013",
    "posh act": "Sexual Harassment of Women at Workplace Act, 2013",
    "sexual harassment": "Sexual Harassment of Women at Workplace Act, 2013",
    "sma": "Special Marriage Act, 1954",
    "special marriage act": "Special Marriage Act, 1954",
}

# Regex to extract section/article numbers from queries
_SECTION_PATTERN = re.compile(
    r'(?:section|article|sec\.?|art\.?)\s+(\d+[a-zA-Z]?)',
    re.IGNORECASE
)


def _extract_section_and_act(query: str) -> tuple[str | None, str | None]:
    """
    Extract section number and act name from a query string.

    Returns (section_number, canonical_source_name) or (None, None).
    Examples:
        "Section 302 IPC" -> ("302", "Indian Penal Code, 1860")
        "CPA Section 273" -> ("273", "Consumer Protection Act, 2019")
        "Article 21 of the Constitution" -> ("21", "Constitution of India")
    """
    section_match = _SECTION_PATTERN.search(query)
    if not section_match:
        return None, None

    section_num = section_match.group(1)

    # Try to match an act name from the query
    query_lower = query.lower()
    matched_source = None
    # Try longest aliases first to avoid partial matches
    for alias in sorted(_ACT_ALIASES.keys(), key=len, reverse=True):
        if alias in query_lower:
            matched_source = _ACT_ALIASES[alias]
            break

    return section_num, matched_source


def _section_metadata_lookup(
    query: str,
    top_k: int = 4,
) -> list[dict]:
    """
    Direct metadata-based section lookup from BM25 corpus.

    Finds chunks where the section field contains the exact section number
    and (optionally) the source matches the act name.

    This bypasses text-based retrieval entirely — it's a structured lookup
    that solves the problem where "Section 302 IPC" retrieves CrPC/CPA chunks
    that mention "302" in passing, instead of the actual IPC 302 chunk.
    """
    section_num, source_name = _extract_section_and_act(query)
    if not section_num:
        return []

    results = []
    for doc in bm25_index.corpus:
        meta = doc.get("metadata", {})
        doc_section = meta.get("section", "")

        # Check if the section field contains this section number
        # e.g., "Section 302" contains "302"
        if section_num not in doc_section:
            continue

        # More precise check: the number should be a whole word
        # Avoid matching "302" inside "3021" or "1302"
        if not re.search(rf'\b{re.escape(section_num)}\b', doc_section):
            continue

        doc_source = meta.get("source", "")

        # If we identified the act, only include chunks from that act
        if source_name and doc_source != source_name:
            continue

        results.append({
            "chunk_id": meta.get("chunk_id", ""),
            "text": doc["text"],
            "source": doc_source,
            "act_short": meta.get("act_short", ""),
            "section": doc_section,
            "section_title": meta.get("section_title", ""),
            "collection": meta.get("collection", ""),
            "doc_id": meta.get("doc_id", ""),
            "user_id": meta.get("user_id", ""),
            "search_type": "metadata",
        })

    # Return up to top_k results
    print(f"[METADATA] Section lookup: section={section_num}, act={source_name or 'any'} -> {len(results)} chunks")
    return results[:top_k]


def hybrid_search(
    query: str,
    user_id: str | None = None,
    doc_id: str | None = None,
    collections: list[str] | None = None,
    top_k: int = 5,
    rrf_k: int = 5,
) -> list[dict]:
    """
    Run hybrid search: vector + BM25 + section metadata lookup, merged via RRF.

    If doc_id is provided, searches law corpus + that specific user document.
    If doc_id is None, searches ONLY the law corpus (chat-scoped isolation).
    """
    if collections is None:
        if doc_id:
            collections = [settings.QDRANT_LAW_COLLECTION, settings.QDRANT_USER_COLLECTION]
        else:
            collections = [settings.QDRANT_LAW_COLLECTION]

    # 1. Vector search (semantic)
    query_vector = embedder.embed_query(query)
    vector_results = vector_store.search(
        query_vector=query_vector,
        collections=collections,
        user_id=user_id,
        doc_id=doc_id,
        top_k=top_k,
    )

    # 2. BM25 search (keyword)
    bm25_results = bm25_index.search(
        query=query,
        top_k=top_k,
        filter_user_id=user_id,
        filter_doc_id=doc_id,
    )

    # 3. Section metadata lookup (structured)
    section_results = _section_metadata_lookup(query, top_k=4)

    # 4. Reciprocal Rank Fusion (all three lists)
    merged = reciprocal_rank_fusion(
        vector_results=vector_results,
        bm25_results=bm25_results,
        section_results=section_results,
        k=rrf_k,
        top_k=top_k,
    )

    return merged


def reciprocal_rank_fusion(
    vector_results: list[dict],
    bm25_results: list[dict],
    section_results: list[dict] | None = None,
    k: int = 5,
    top_k: int = 5,
) -> list[dict]:
    """
    Merge ranked lists using Reciprocal Rank Fusion.

    RRF Score = Sum of 1/(k + rank) across all result lists.

    Documents that rank well in MULTIPLE searches get the highest combined score.
    Section metadata results get a 1.5x boost since they're exact structural matches.

    Args:
        vector_results: Results from Qdrant vector search
        bm25_results: Results from BM25 keyword search
        section_results: Results from metadata section lookup (optional)
        k: RRF constant (default 5)
        top_k: Number of results to return

    Returns:
        Merged and re-ranked results with RRF score
    """
    scores: dict[str, float] = {}
    doc_data: dict[str, dict] = {}

    # Score vector results
    for rank, result in enumerate(vector_results):
        chunk_id = result.get("chunk_id", f"vec_{rank}")
        rrf_score = 1.0 / (k + rank + 1)
        scores[chunk_id] = scores.get(chunk_id, 0) + rrf_score

        if chunk_id not in doc_data:
            doc_data[chunk_id] = result.copy()
            doc_data[chunk_id]["vector_rank"] = rank + 1
            doc_data[chunk_id]["vector_score"] = result.get("score", 0)
        else:
            doc_data[chunk_id]["vector_rank"] = rank + 1
            doc_data[chunk_id]["vector_score"] = result.get("score", 0)

    # Score BM25 results
    for rank, result in enumerate(bm25_results):
        chunk_id = result.get("chunk_id", f"bm25_{rank}")
        rrf_score = 1.0 / (k + rank + 1)
        scores[chunk_id] = scores.get(chunk_id, 0) + rrf_score

        if chunk_id not in doc_data:
            doc_data[chunk_id] = result.copy()
            doc_data[chunk_id]["bm25_rank"] = rank + 1
            doc_data[chunk_id]["bm25_score"] = result.get("bm25_score", 0)
        else:
            doc_data[chunk_id]["bm25_rank"] = rank + 1
            doc_data[chunk_id]["bm25_score"] = result.get("bm25_score", 0)

    # Score section metadata results (1.5x boost — exact structural matches)
    if section_results:
        for rank, result in enumerate(section_results):
            chunk_id = result.get("chunk_id", f"meta_{rank}")
            rrf_score = 1.5 / (k + rank + 1)  # 1.5x boost for metadata matches
            scores[chunk_id] = scores.get(chunk_id, 0) + rrf_score

            if chunk_id not in doc_data:
                doc_data[chunk_id] = result.copy()
                doc_data[chunk_id]["metadata_rank"] = rank + 1
            else:
                doc_data[chunk_id]["metadata_rank"] = rank + 1

    # Sort by RRF score
    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

    # Build final results
    results = []
    for chunk_id in sorted_ids[:top_k]:
        entry = doc_data[chunk_id]
        entry["rrf_score"] = scores[chunk_id]
        entry["search_type"] = "hybrid"

        # Clean up: remove internal BM25/vector scores from final output
        entry.pop("score", None)

        results.append(entry)

    return results


def vector_only_search(
    query: str,
    user_id: str | None = None,
    doc_id: str | None = None,
    collections: list[str] | None = None,
    top_k: int = 5,
) -> list[dict]:
    """
    Vector-only search (for testing/comparison against hybrid).
    """
    query_vector = embedder.embed_query(query)
    return vector_store.search(
        query_vector=query_vector,
        collections=collections,
        user_id=user_id,
        doc_id=doc_id,
        top_k=top_k,
    )


def bm25_only_search(
    query: str,
    user_id: str | None = None,
    top_k: int = 5,
) -> list[dict]:
    """
    BM25-only search (for testing/comparison against hybrid).
    """
    return bm25_index.search(
        query=query,
        top_k=top_k,
        filter_user_id=user_id,
    )
