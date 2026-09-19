# LexAI Backend

The backend service for LexAI provides an asynchronous FastAPI application running a cyclic LangGraph state machine. It handles hybrid dense-sparse retrieval across Indian statutory law, document OCR extraction, conversational session management, and self-correcting validation.

For the project overview, visit the [Main Documentation](../README.md). For detailed performance benchmarks and latency evaluations, see the [Engineering Case Study](../CASE_STUDY.md).

---

## Technical Stack

- **Application Framework**: FastAPI (Python 3.13) with asynchronous request handlers.
- **Workflow State Machine**: LangGraph (`StateGraph`).
- **Dependency Management**: Astral `uv`.
- **Vector Store**: Qdrant (1024-dimensional dense vectors with cosine metric).
- **Keyword Retrieval**: `rank-bm25` (BM25Plus with legal term preservation).
- **Rank Fusion**: Reciprocal Rank Fusion (RRF, k=5).
- **Embeddings**: `BAAI/bge-m3` supporting dual operational modes (local SentenceTransformer for ingestion, Hugging Face Inference API for server runtime).
- **LLM Reasoning**: Groq API (`openai/gpt-oss-20b` / `qwen/qwen3.6-27b`).
- **Web Search Fallback**: Tavily Search API.
- **Document Loading & OCR**: PyMuPDF (`fitz`) with Tesseract OCR fallback for scanned legal documents.
- **Persistence & Auth**: Supabase PostgreSQL and Supabase Auth.

---

## LangGraph Workflow Architecture

The core pipeline is implemented as a cyclic directed state graph in `app/graph/workflow.py`:

```
                 [__start__]
                      |
                      v
                [route_input]
               /             \
        (valid legal)       (harmful / non-legal)
             |                       |
             v                       v
    [contextualize_query]         [reject] ---> [__end__]
             |
             v
         [retrieve] <------------------+
             |                         |
             v                         | (retries < 2)
        [grade_docs]                   |
       /      |     \                  |
 (adequate)   |   (low quality)        |
    |         |         |              |
    |         |         +-----> [rewrite_query]
    |         |
    |         +---------------> [web_search] (corpus empty fallback)
    |                                  |
    v                                  v
 [generate] <--------------------------+
    |
    v
 [check_hallucination]
    |
    v
 [format_response] ---> [__end__]
```

### Node Responsibilities

- **`route_input`**: Evaluates incoming queries against domain and safety guardrails. Out-of-scope or toxic inputs route directly to `reject`.
- **`contextualize_query`**: Analyzes the last 3 turns of conversation history to resolve pronouns and references into a standalone legal query.
- **`retrieve`**: Concurrently queries Qdrant (vector) and BM25Plus (keyword), combining results via Reciprocal Rank Fusion.
- **`grade_docs`**: Concurrently evaluates retrieved chunks via multi-threaded LLM calls (`ThreadPoolExecutor`) to confirm factual relevance to the query.
- **`rewrite_query`**: Reformulates the search query with legal synonyms if retrieved context is insufficient (up to 2 retries).
- **`web_search`**: Invokes Tavily Web Search if the statutory corpus does not contain sufficient information for the query.
- **`generate`**: Synthesizes a structured legal response citing specific statutory sections.
- **`check_hallucination`**: Confirms that legal assertions made in the answer are grounded in retrieved context.
- **`format_response`**: Structures the final Markdown response with statutory citations and legal disclaimers.

---

## Dual-Mode Embedding and Pre-Indexed BM25

To balance developer efficiency with low-memory deployment constraints:

1. **Dual-Mode Embedding (`BAAI/bge-m3`)**:
   - **Ingestion (`--local`)**: Ingestion runs locally using PyTorch `SentenceTransformer` to batch-vectorize ~7,800 statutory chunks without API rate limits.
   - **Server Runtime (`EMBEDDING_MODE=api`)**: The running API server queries the Hugging Face Inference API, maintaining a compact memory footprint of ~150MB by not loading the 2.2GB model weights into server RAM.
2. **Pre-Indexed BM25 Index**:
   - The BM25Plus index is precomputed and saved as `data/bm25_index.pkl` (13.5MB).
   - This allows the backend to initialize keyword search instantly on startup without re-parsing statutory PDFs.

---

## Directory Structure

```text
backend/
|-- app/
|   |-- graph/
|   |   |-- state.py              # TypedDict RAGState definition
|   |   |-- nodes.py              # LangGraph execution nodes
|   |   |-- edges.py              # Routing conditionals
|   |   `-- workflow.py           # StateGraph definition and compilation
|   |-- prompts/
|   |   `-- system_prompt.py      # LLM prompts for generation, grading, and routing
|   |-- routers/
|   |   |-- query.py              # POST /api/query (single-turn RAG)
|   |   |-- chat.py               # POST /api/chat (multi-turn RAG with Supabase)
|   |   |-- upload.py             # POST /api/upload (document parsing and indexing)
|   |   `-- health.py             # GET /health
|   |-- services/
|   |   |-- hybrid_retriever.py   # RRF fusion engine
|   |   |-- vector_store.py       # Qdrant client wrapper
|   |   |-- bm25_search.py        # BM25Plus index manager
|   |   |-- embedder.py           # Dual-mode bge-m3 wrapper
|   |   |-- doc_loader.py         # PyMuPDF and OCR reader
|   |   |-- chunker.py            # Legal structure-aware section chunker
|   |   |-- web_search.py         # Tavily web search service
|   |   `-- supabase_service.py   # Chat persistence client
|   |-- config.py                 # Pydantic v2 application settings
|   `-- main.py                   # FastAPI initialization and lifespan
|-- data/
|   |-- corpus/                   # Raw Indian Law PDFs
|   `-- bm25_index.pkl            # Precomputed BM25 index
|-- scripts/
|   |-- ingest_corpus.py          # PDF parsing, chunking, and Qdrant ingestion
|   |-- check_qdrant.py           # Qdrant collection inspector
|   |-- migrate_qdrant.py         # Vector migration utility
|   `-- chat_schema.sql           # Supabase PostgreSQL schema definition
|-- Dockerfile                    # Multi-stage production container build
|-- langgraph.json                # LangGraph Studio dev server configuration
|-- pyproject.toml                # Dependencies managed by uv
`-- uv.lock                       # Deterministic lockfile
```

---

## Local Setup and Execution

### 1. Install Dependencies

```powershell
cd backend
uv sync
```

### 2. Configure Environment

Copy `.env.example` to `.env`:

```powershell
cp .env.example .env
```

Ensure the following variables are configured in `backend/.env`:

```ini
ENVIRONMENT=development
FRONTEND_ORIGIN=http://localhost:5173

# Qdrant: Local Docker or Qdrant Cloud
QDRANT_HOST=localhost
QDRANT_PORT=6333
# QDRANT_URL=
# QDRANT_API_KEY=

# Groq LLM
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=openai/gpt-oss-20b

# Embeddings: local or api
EMBEDDING_MODE=local
EMBEDDING_MODEL=BAAI/bge-m3
HF_API_TOKEN=your_huggingface_token

# Supabase Auth and Database
SUPABASE_URL=your_supabase_url
SUPABASE_SERVICE_KEY=your_supabase_service_role_key

# Web Search Fallback
TAVILY_API_KEY=your_tavily_api_key
```

### 3. Start Qdrant Vector Store

```powershell
docker run -d -p 6333:6333 -p 6334:6334 -v qdrant_storage:/qdrant/storage qdrant/qdrant:latest
```

### 4. Corpus Ingestion (Required for Fresh Setup)

When running Qdrant locally for the first time, the vector database starts empty. Ingest the 16 statutory PDFs from `data/corpus/` into your local Qdrant container:

```powershell
uv run python scripts/ingest_corpus.py --wipe --local
```

*(Note: If connecting to an already populated Qdrant Cloud cluster via `QDRANT_URL` and `QDRANT_API_KEY`, this step can be skipped.)*

### 5. Run Backend Server

```powershell
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Swagger UI: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

---

## Visual Graph Inspection (LangGraph Studio)

To inspect nodes, conditional edges, and execution state in real time:

```powershell
$env:PYTHONIOENCODING="utf-8"; uv run langgraph dev
```

Open the printed studio URL in your browser to test execution graphs with custom state payloads.

---

## API Reference

| Endpoint | Method | Request Body | Response | Purpose |
|---|---|---|---|---|
| `/health` | `GET` | None | `{"status": "ok", "services": {...}}` | Connectivity check for Qdrant, BM25, and Embedder. |
| `/api/query` | `POST` | `{"query": str, "doc_id": Optional[str]}` | `{"answer": str, "citations": list}` | Single-turn RAG query against law corpus and/or uploaded document. |
| `/api/chat` | `POST` | `{"query": str, "session_id": str, "doc_id": Optional[str]}` | `{"answer": str, "citations": list}` | Multi-turn conversational query with Supabase history. |
| `/api/upload` | `POST` | Multipart Form: `file` | `{"doc_id": str, "filename": str, "chunks": int}` | Uploads PDF/image, runs OCR fallback, chunks, and indexes. |
