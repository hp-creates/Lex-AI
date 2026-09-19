"""
Embedding Service — dual-mode embedder for legal-bge-m3.

Two modes, controlled by EMBEDDING_MODE env var:

  "local" — Loads SentenceTransformer model into memory (~2.2GB).
            Used for corpus ingestion on your local machine.
            No API calls, no rate limits, fastest throughput.

  "api"   — Calls HuggingFace Inference API. Zero RAM footprint.
            Used on EC2 for runtime queries + user document uploads.

Model: yuriyvnv/legal-bge-m3
- Fine-tuned on 400K rows of legal data (LEGALBENCH-RAG)
- Dimensions: 1024
- Base: BAAI/bge-m3

IMPORTANT: Both modes use the SAME model weights, producing identical
vectors. Corpus ingested locally is fully compatible with API-mode queries.
"""

import math
import time

import httpx

from app.config import settings


class Embedder:
    """Dual-mode embedding client: local SentenceTransformer or HF Inference API."""

    _model = None          # SentenceTransformer instance (local mode only)
    _mode: str = "api"
    # _mode: str = "local"
    _ready: bool = False
    _dimensions: int = 1024

    def load(self):
        """
        Initialize the embedder based on EMBEDDING_MODE.
        - "local": downloads and loads the model into RAM (~2.2GB)
        - "api": validates HF token and tests API connectivity (instant)
        """
        self._mode = settings.EMBEDDING_MODE

        if self._mode == "local":
            self._load_local()
        elif self._mode == "api":
            self._load_api()
        else:
            raise ValueError(f"Invalid EMBEDDING_MODE: '{self._mode}'. Use 'local' or 'api'.")

        self._ready = True

    def _load_local(self):
        """Load SentenceTransformer model into memory."""
        from sentence_transformers import SentenceTransformer

        model_name = settings.EMBEDDING_MODEL
        print(f"[EMBEDDER] Loading local model: {model_name}...")

        self._model = SentenceTransformer(
            model_name,
            trust_remote_code=True,
            device="cpu",
        )

        # Warm up + detect dimensions
        test = self._model.encode(["test"], normalize_embeddings=True)
        self._dimensions = len(test[0])
        print(f"[EMBEDDER] Local model ready. Dimensions: {self._dimensions}")

    def _load_api(self):
        """Validate HF API token and test connectivity."""
        if not settings.HF_API_TOKEN:
            raise RuntimeError(
                "HF_API_TOKEN is not set. Get one at https://huggingface.co/settings/tokens"
            )

        print(f"[EMBEDDER] Verifying HF Inference API ({settings.EMBEDDING_MODEL})...")
        test_result = self._call_hf_api(["connectivity test"])
        self._dimensions = len(test_result[0])
        print(f"[EMBEDDER] HF API ready. Dimensions: {self._dimensions}")

    @property
    def is_loaded(self) -> bool:
        return self._ready

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
        if not self._ready:
            raise RuntimeError("Embedder not ready. Call embedder.load() first.")

        if not texts:
            return []

        if self._mode == "local":
            return self._embed_local(texts)
        return self._call_hf_api(texts)

    def embed_query(self, query: str) -> list[float]:
        """
        Embed a single query string.

        Args:
            query: Search query to embed

        Returns:
            Embedding vector (list of floats)
        """
        if not self._ready:
            raise RuntimeError("Embedder not ready. Call embedder.load() first.")

        if self._mode == "local":
            return self._embed_local([query])[0]
        return self._call_hf_api([query])[0]

    # --- Local mode ---

    def _embed_local(self, texts: list[str]) -> list[list[float]]:
        """Embed using the in-memory SentenceTransformer model."""
        vectors = self._model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vectors.tolist()

    # --- API mode ---

    def _call_hf_api(
        self,
        texts: list[str],
        max_retries: int = 5,
    ) -> list[list[float]]:
        """
        Call the HuggingFace Inference API with retry logic.

        Args:
            texts: Texts to embed
            max_retries: Number of retry attempts on failure

        Returns:
            List of normalized embedding vectors
        """
        # HuggingFace migrated from api-inference.huggingface.co (deprecated, DNS removed)
        # to router.huggingface.co/hf-inference/models/{model}/pipeline/feature-extraction
        url = f"https://router.huggingface.co/hf-inference/models/{settings.EMBEDDING_MODEL}/pipeline/feature-extraction"
        headers = {
            "Authorization": f"Bearer {settings.HF_API_TOKEN}",
            "Content-Type": "application/json",
        }

        payload = {
            "inputs": texts,
            "options": {"wait_for_model": True},
        }

        last_error = None

        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=120.0) as client:
                    response = client.post(url, headers=headers, json=payload)

                if response.status_code == 200:
                    data = response.json()
                    return self._parse_hf_response(data, len(texts))

                # Model is loading — wait and retry
                if response.status_code == 503:
                    wait = min(30, 5 * (attempt + 1))
                    print(f"[EMBEDDER] Model loading on HF. Waiting {wait}s...")
                    time.sleep(wait)
                    last_error = f"Model loading (503)"
                    continue

                # Rate limit
                if response.status_code == 429:
                    wait = 10 * (attempt + 1)
                    print(f"[EMBEDDER] Rate limited. Waiting {wait}s...")
                    time.sleep(wait)
                    last_error = f"Rate limited (429): {response.text[:200]}"
                    continue

                last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                print(f"[EMBEDDER] API error: {last_error}")

            except httpx.TimeoutException:
                wait = 10 * (attempt + 1)
                last_error = f"Timeout after 120s (attempt {attempt + 1})"
                print(f"[EMBEDDER] {last_error}. Retrying in {wait}s...")
                time.sleep(wait)

            except Exception as e:
                last_error = str(e)
                print(f"[EMBEDDER] Unexpected error: {last_error}")
                break

        raise RuntimeError(f"HF API call failed after {max_retries} attempts: {last_error}")

    def _parse_hf_response(self, data: list, expected_count: int) -> list[list[float]]:
        """
        Parse HF Inference API response and normalize embeddings.

        HF feature-extraction can return either:
        - Sentence embeddings: [[float, ...], [float, ...]]       (ideal)
        - Per-token embeddings: [[[float, ...], ...], ...]         (needs pooling)
        """
        if not data:
            raise RuntimeError("Empty response from HF API")

        # Check if response is sentence-level or token-level
        first = data[0]

        if isinstance(first, list) and len(first) > 0 and isinstance(first[0], list):
            # Per-token embeddings: mean-pool each sequence
            embeddings = []
            for token_embeddings in data:
                pooled = [
                    sum(dim_vals) / len(dim_vals)
                    for dim_vals in zip(*token_embeddings)
                ]
                embeddings.append(self._normalize(pooled))
            return embeddings
        else:
            # Already sentence-level embeddings
            return [self._normalize(emb) for emb in data]

    @staticmethod
    def _normalize(vector: list[float]) -> list[float]:
        """L2-normalize a vector for cosine similarity."""
        norm = math.sqrt(sum(x * x for x in vector))
        if norm == 0:
            return vector
        return [x / norm for x in vector]


# Global singleton — import this everywhere
embedder = Embedder()
