"""
Embedding Service — singleton Jina v3 model loader.

Loads the embedding model ONCE at startup. All subsequent embed calls
reuse the same model instance (no re-loading per request).

Model: jinaai/jina-embeddings-v3
- Dimensions: 1024
- Optimized for legal/technical text
- ~800MB model size
- Runs on CPU (no GPU required on t3.medium)

Uses sentence-transformers directly (bypasses langchain-huggingface)
to avoid transformers version incompatibilities with Jina's custom code.

IMPORTANT: This model is LOCKED after corpus ingestion. All vectors in
Qdrant must use the same model. Switching requires full re-ingestion.
"""

from sentence_transformers import SentenceTransformer


class Embedder:
    """Singleton embedding model wrapper."""

    _model: SentenceTransformer | None = None
    _model_name: str = "jinaai/jina-embeddings-v3"
    _dimensions: int = 1024

    def load(self, model_name: str | None = None):
        """
        Load the embedding model into memory. Call once at startup.

        Args:
            model_name: Override the default model (for testing)
        """
        if model_name:
            self._model_name = model_name

        print(f"[EMBEDDER] Loading model: {self._model_name}...")

        self._model = SentenceTransformer(
            self._model_name,
            trust_remote_code=True,
            device="cpu",
        )

        # Warm up + detect dimensions
        test = self._model.encode(["test"], normalize_embeddings=True)
        self._dimensions = len(test[0])

        print(f"[EMBEDDER] Model loaded. Dimensions: {self._dimensions}")

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a list of document chunks.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors (each is a list of floats)
        """
        if not self._model:
            raise RuntimeError("Embedder not loaded. Call embedder.load() first.")

        # Jina v3 uses task-specific prompts; "retrieval.passage" for indexing
        vectors = self._model.encode(
            texts,
            task="retrieval.passage",
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vectors.tolist()

    def embed_query(self, query: str) -> list[float]:
        """
        Embed a single query string.

        Args:
            query: Search query to embed

        Returns:
            Embedding vector (list of floats)
        """
        if not self._model:
            raise RuntimeError("Embedder not loaded. Call embedder.load() first.")

        # Jina v3 uses task-specific prompts; "retrieval.query" for queries
        vector = self._model.encode(
            [query],
            task="retrieval.query",
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vector[0].tolist()


# Global singleton — import this everywhere
embedder = Embedder()
