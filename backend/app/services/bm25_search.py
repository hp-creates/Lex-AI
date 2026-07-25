"""
BM25 Keyword Search — custom incremental index.

Why BM25 alongside vector search?
Legal documents contain statute numbers ("Section 302"), acronyms ("IPC", "CrPC"),
and exact names that pure semantic/vector search misses. BM25 catches these exact
keyword matches.

Key features:
- Incremental updates (add/remove docs without full rebuild)
- Persistence to disk (pickle) across restarts
- User-scoped filtering
- Collection-aware (law corpus + user docs in same index)
"""

import pickle
import re
from pathlib import Path

from rank_bm25 import BM25Plus

from app.config import settings


class IncrementalBM25:
    """BM25 index that supports adding documents without full rebuild."""

    def __init__(self, persist_path: str | None = None):
        self.persist_path = Path(persist_path or settings.BM25_INDEX_PATH)
        self.corpus: list[dict] = []                  # {"text": str, "metadata": dict}
        self.tokenized_corpus: list[list[str]] = []
        self._index: BM25Plus | None = None

    def add_documents(self, docs: list[dict]):
        """
        Add new documents and rebuild the BM25 index.

        The rebuild is fast for our scale (<50K docs).
        BM25Okapi requires the full tokenized corpus to compute IDF.

        Args:
            docs: List of dicts with 'text' and 'metadata' keys
        """
        for doc in docs:
            self.corpus.append(doc)
            self.tokenized_corpus.append(self._tokenize(doc["text"]))

        # Rebuild index with updated corpus
        if self.tokenized_corpus:
            self._index = BM25Plus(self.tokenized_corpus)

        self._persist()

    def search(
        self,
        query: str,
        top_k: int = 5,
        filter_user_id: str | None = None,
        filter_collection: str | None = None,
    ) -> list[dict]:
        """
        Search the BM25 index.

        Args:
            query: Search query string
            top_k: Number of results to return
            filter_user_id: Only return docs from this user (+ law corpus)
            filter_collection: Only return docs from this collection

        Returns:
            List of results with doc data and BM25 score
        """
        if not self._index or not self.corpus:
            return []

        tokenized_query = self._tokenize(query)
        scores = self._index.get_scores(tokenized_query)

        # Build scored results with filtering
        scored_docs = []
        for i, score in enumerate(scores):
            if score <= 0:
                continue  # Skip zero-score docs

            doc = self.corpus[i]
            meta = doc.get("metadata", {})

            # Apply user filter: show law corpus to everyone, user docs only to owner
            if filter_user_id:
                doc_collection = meta.get("collection", "")
                doc_user_id = meta.get("user_id", "")
                if doc_collection == "user_documents" and doc_user_id != filter_user_id:
                    continue

            # Apply collection filter
            if filter_collection and meta.get("collection", "") != filter_collection:
                continue

            scored_docs.append({
                "chunk_id": meta.get("chunk_id", ""),
                "text": doc["text"],
                "bm25_score": float(score),
                "source": meta.get("source", ""),
                "act_short": meta.get("act_short", ""),
                "section": meta.get("section", ""),
                "section_title": meta.get("section_title", ""),
                "collection": meta.get("collection", ""),
                "doc_id": meta.get("doc_id", ""),
                "user_id": meta.get("user_id", ""),
                "search_type": "bm25",
            })

        # Sort by BM25 score descending
        scored_docs.sort(key=lambda x: x["bm25_score"], reverse=True)
        return scored_docs[:top_k]

    def remove_by_doc_id(self, doc_id: str):
        """
        Remove all chunks for a document and rebuild the index.

        Args:
            doc_id: Document UUID to remove
        """
        self.corpus = [
            d for d in self.corpus
            if d.get("metadata", {}).get("doc_id", "") != doc_id
        ]
        self.tokenized_corpus = [self._tokenize(d["text"]) for d in self.corpus]

        if self.tokenized_corpus:
            self._index = BM25Plus(self.tokenized_corpus)
        else:
            self._index = None

        self._persist()

    # Alias for remove_by_doc_id
    remove_document = remove_by_doc_id

    def clear(self):
        """Clear the entire index."""
        self.corpus = []
        self.tokenized_corpus = []
        self._index = None
        self._persist()

    @property
    def doc_count(self) -> int:
        return len(self.corpus)

    def _tokenize(self, text: str) -> list[str]:
        """
        Tokenize text for BM25.

        Simple whitespace + punctuation split. Lowercased.
        Keeps numbers and legal terms intact (e.g., "302", "ipc").
        """
        # Lowercase and split on non-alphanumeric characters
        tokens = re.findall(r'\b\w+\b', text.lower())
        return tokens

    def _persist(self):
        """Save index to disk."""
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.persist_path, "wb") as f:
            pickle.dump({
                "corpus": self.corpus,
                "tokens": self.tokenized_corpus,
            }, f)

    def load(self):
        """Load index from disk."""
        if self.persist_path.exists():
            with open(self.persist_path, "rb") as f:
                data = pickle.load(f)
                self.corpus = data.get("corpus", [])
                self.tokenized_corpus = data.get("tokens", [])

                if self.tokenized_corpus:
                    self._index = BM25Plus(self.tokenized_corpus)

            print(f"[BM25] Loaded index: {self.doc_count} documents")
        else:
            print("[BM25] No persisted index found. Starting fresh.")


# Global singleton
bm25_index = IncrementalBM25()
