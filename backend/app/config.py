"""
LexAI Configuration — loads all environment variables via Pydantic Settings.
Single source of truth for all config. Never hardcode secrets anywhere else.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    # === App ===
    APP_NAME: str = "LexAI"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = Field(default="development", description="development | production")
    FRONTEND_ORIGIN: str = Field(default="http://localhost:5173", description="CORS allowed origin")

    # === Qdrant ===
    # Cloud mode: set QDRANT_URL + QDRANT_API_KEY (overrides host/port)
    # Local mode: use QDRANT_HOST + QDRANT_PORT (Docker dev)
    QDRANT_URL: str = Field(default="", description="Qdrant Cloud URL (overrides host:port when set)")
    QDRANT_API_KEY: str = Field(default="", description="Qdrant Cloud API key")
    QDRANT_HOST: str = Field(default="localhost", description="Docker service name or localhost")
    QDRANT_PORT: int = Field(default=6333, description="Qdrant REST API port")
    QDRANT_LAW_COLLECTION: str = "indian_law_corpus"
    QDRANT_USER_COLLECTION: str = "user_documents"

    # === Groq (LLM) ===
    GROQ_API_KEY: str = Field(default="", description="Groq API key")
    GROQ_MODEL: str = "openai/gpt-oss-20b"  # GPT OSS reasoning model on Groq (llama-3.3-70b deprecated)

    # === Embedding Model (bge-m3) ===
    # Server runtime uses "api" (HF Inference API, zero RAM).
    # Corpus ingestion uses "local" via --local flag in ingest_corpus.py.
    EMBEDDING_MODE: str = Field(default="api", description="'local' or 'api'")
    EMBEDDING_MODEL: str = Field(default="BAAI/bge-m3", description="HuggingFace model name")
    HF_API_TOKEN: str = Field(default="", description="HuggingFace API token (required for api mode)")

    # === Supabase (Auth + DB) — needed in Stage 3+ ===
    SUPABASE_URL: str = Field(default="", description="Supabase project URL")
    SUPABASE_ANON_KEY: str = Field(default="", description="Public anon key (safe for frontend)")
    SUPABASE_SERVICE_KEY: str = Field(default="", description="Server-side service role key")

    # === BM25 ===
    BM25_INDEX_PATH: str = Field(default="data/bm25_index.pkl", description="Path to persisted BM25 index")

    # === Tavily (Web Search Fallback) ===
    TAVILY_API_KEY: str = Field(default="", description="Tavily API key for web search fallback")

    # ==========================================
    # LangSmith Tracing
    # ==========================================
    LANGCHAIN_TRACING_V2: str = Field(default="false", description="Enable LangSmith Tracing")
    LANGCHAIN_ENDPOINT: str = Field(default="https://api.smith.langchain.com", description="LangSmith API Endpoint")
    LANGCHAIN_API_KEY: str = Field(default="", description="LangSmith API Key")
    LANGCHAIN_PROJECT: str = Field(default="lex-ai", description="LangSmith Project Name")
    # ==========================================

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# Global settings instance — import this everywhere
settings = Settings()

