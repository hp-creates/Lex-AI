"""
Vector Store Service — Qdrant client wrapper.

Handles:
- Collection creation (idempotent)
- Upserting chunks with embeddings + metadata
- Searching across collections
- Deleting chunks by doc_id

Qdrant runs as a Docker container on the same EC2 instance.
Connection is via Docker service name or localhost.
"""

import uuid

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    Filter,
    FieldCondition,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.config import settings


class VectorStore:
    """Qdrant vector database wrapper."""

    _client: QdrantClient | None = None

    def init_client(self):
        """Connect to Qdrant. Call once at startup."""
        self._client = QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            timeout=30,
        )
        print(f"[QDRANT] Connected to {settings.QDRANT_HOST}:{settings.QDRANT_PORT}")

    @property
    def client(self) -> QdrantClient:
        if not self._client:
            raise RuntimeError("VectorStore not initialized. Call init_client() first.")
        return self._client

    def create_collections(self, vector_size: int = 1024):
        """
        Create both collections if they don't already exist.
        Idempotent — safe to call multiple times.

        Args:
            vector_size: Embedding dimension (1024 for Jina v3)
        """
        existing = [c.name for c in self.client.get_collections().collections]

        for collection_name in [settings.QDRANT_LAW_COLLECTION, settings.QDRANT_USER_COLLECTION]:
            if collection_name not in existing:
                self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=vector_size,
                        distance=Distance.COSINE,
                    ),
                )
                print(f"[QDRANT] Created collection: {collection_name}")
            else:
                print(f"[QDRANT] Collection already exists: {collection_name}")

    def upsert_chunks(
        self,
        collection: str,
        chunks: list[dict],
        embeddings: list[list[float]],
    ) -> int:
        """
        Upsert chunks with their embeddings into a Qdrant collection.

        Uses deterministic UUIDs based on chunk_id so re-running is idempotent.

        Args:
            collection: Collection name
            chunks: List of dicts with 'text' and 'metadata' keys
            embeddings: List of embedding vectors (must match chunks length)

        Returns:
            Number of points upserted
        """
        if len(chunks) != len(embeddings):
            raise ValueError(f"Chunks ({len(chunks)}) and embeddings ({len(embeddings)}) must have same length")

        points = []
        for chunk, embedding in zip(chunks, embeddings):
            # Deterministic UUID from chunk_id for idempotent upserts
            chunk_id = chunk["metadata"].get("chunk_id", str(uuid.uuid4()))
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk_id))

            payload = {
                "text": chunk["text"],
                **chunk["metadata"],
            }

            points.append(PointStruct(
                id=point_id,
                vector=embedding,
                payload=payload,
            ))

        # Batch upsert (Qdrant handles batching internally)
        BATCH_SIZE = 100
        for i in range(0, len(points), BATCH_SIZE):
            batch = points[i:i + BATCH_SIZE]
            self.client.upsert(
                collection_name=collection,
                points=batch,
            )

        return len(points)

    def search(
        self,
        query_vector: list[float],
        collections: list[str] | None = None,
        user_id: str | None = None,
        doc_id: str | None = None,
        top_k: int = 5,
    ) -> list[dict]:
        """
        Search across one or more collections.

        Args:
            query_vector: Query embedding
            collections: Collections to search (defaults to both)
            user_id: Filter user_documents by user_id
            doc_id: Filter by specific document
            top_k: Number of results per collection

        Returns:
            List of results with text, metadata, and cosine score
        """
        if collections is None:
            collections = [settings.QDRANT_LAW_COLLECTION, settings.QDRANT_USER_COLLECTION]

        all_results = []

        for collection in collections:
            # Build filter for user_documents
            query_filter = None
            if collection == settings.QDRANT_USER_COLLECTION:
                conditions = []
                if user_id:
                    conditions.append(
                        FieldCondition(key="user_id", match=MatchValue(value=user_id))
                    )
                if doc_id:
                    conditions.append(
                        FieldCondition(key="doc_id", match=MatchValue(value=doc_id))
                    )
                if conditions:
                    query_filter = Filter(must=conditions)

            try:
                results = self.client.search(
                    collection_name=collection,
                    query_vector=query_vector,
                    limit=top_k,
                    query_filter=query_filter,
                    with_payload=True,
                )

                for hit in results:
                    all_results.append({
                        "chunk_id": hit.payload.get("chunk_id", ""),
                        "text": hit.payload.get("text", ""),
                        "score": hit.score,
                        "source": hit.payload.get("source", ""),
                        "act_short": hit.payload.get("act_short", ""),
                        "section": hit.payload.get("section", ""),
                        "section_title": hit.payload.get("section_title", ""),
                        "collection": collection,
                        "doc_id": hit.payload.get("doc_id", ""),
                        "user_id": hit.payload.get("user_id", ""),
                        "search_type": "vector",
                    })
            except Exception as e:
                print(f"[QDRANT] Search error in {collection}: {e}")

        # Sort by score descending
        all_results.sort(key=lambda x: x["score"], reverse=True)
        return all_results[:top_k]

    def delete_by_doc_id(self, collection: str, doc_id: str) -> bool:
        """
        Delete all chunks belonging to a document from Qdrant.

        Args:
            collection: Collection name
            doc_id: Document UUID

        Returns:
            True if deletion was successful
        """
        from qdrant_client.http.models import FilterSelector
        try:
            # First try with FilterSelector
            self.client.delete(
                collection_name=collection,
                points_selector=FilterSelector(
                    filter=Filter(
                        must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
                    )
                ),
            )
            print(f"[QDRANT] Deleted points for doc_id: {doc_id} from {collection}")
            return True
        except Exception as e:
            # Fallback for direct Filter
            try:
                self.client.delete(
                    collection_name=collection,
                    points_selector=Filter(
                        must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
                    ),
                )
                print(f"[QDRANT] Deleted points for doc_id: {doc_id} from {collection} (fallback)")
                return True
            except Exception as e2:
                print(f"[QDRANT] Delete error: {e2}")
                return False

    def get_collection_info(self, collection: str) -> dict:
        """Get collection stats (point count, etc.)."""
        try:
            info = self.client.get_collection(collection)
            return {
                "name": collection,
                "points_count": info.points_count,
                "indexed_vectors_count": info.indexed_vectors_count,
                "status": info.status.value if info.status else "unknown",
            }
        except Exception as e:
            return {"name": collection, "error": str(e)}


# Global singleton
vector_store = VectorStore()
