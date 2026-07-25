"""
Hybrid Retriever — combines Vector (Qdrant) + BM25 search via Reciprocal Rank Fusion.

Pipeline:
1. Embed query -> vector search (Qdrant) -> semantic matches
2. Tokenize query -> BM25 search -> keyword/exact matches
3. Reciprocal Rank Fusion (RRF) merges both, docs good in BOTH rise to top

Why hybrid?
- Vector search catches meaning ("right to defend" -> Section 96)
- BM25 catches exact terms ("Section 302 IPC" -> exact match)
- RRF ensures docs ranked well in BOTH searches are prioritized

k = 5 (RRF constant). Higher k = more uniform weight across ranks.
"""

from app.services.vector_store import vector_store
from app.services.bm25_search import bm25_index
from app.services.embedder import embedder


def hybrid_search(
    query: str,
    user_id: str | None = None,
    doc_id: str | None = None,
    collections: list[str] | None = None,
    top_k: int = 5,
    rrf_k: int = 5,
) -> list[dict]:
    """
    Run hybrid search: vector + BM25, merged via Reciprocal Rank Fusion.

    Args:
        query: User's question
        user_id: Filter user docs by owner
        doc_id: Filter by specific document
        collections: Which Qdrant collections to search
        top_k: Number of final results to return
        rrf_k: RRF constant (higher = more uniform ranking)

    Returns:
        List of merged results sorted by RRF score
    """
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
    )

    # 3. Reciprocal Rank Fusion
    merged = reciprocal_rank_fusion(
        vector_results=vector_results,
        bm25_results=bm25_results,
        k=rrf_k,
        top_k=top_k,
    )

    return merged


def reciprocal_rank_fusion(
    vector_results: list[dict],
    bm25_results: list[dict],
    k: int = 5,
    top_k: int = 5,
) -> list[dict]:
    """
    Merge two ranked lists using Reciprocal Rank Fusion.

    RRF Score = Sum of 1/(k + rank) across all result lists.

    Documents that rank well in BOTH searches get the highest combined score.

    Args:
        vector_results: Results from Qdrant vector search
        bm25_results: Results from BM25 keyword search
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
