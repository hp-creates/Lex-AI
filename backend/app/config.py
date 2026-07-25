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

    # === Qdrant (self-hosted in Docker) ===
    QDRANT_HOST: str = Field(default="localhost", description="Docker service name or localhost")
    QDRANT_PORT: int = Field(default=6333, description="Qdrant REST API port")
    QDRANT_LAW_COLLECTION: str = "indian_law_corpus"
    QDRANT_USER_COLLECTION: str = "user_documents"

    # === Groq (LLM) — needed in Stage 2+ ===
    GROQ_API_KEY: str = Field(default="", description="Groq API key for LLaMA 3.3 70B")
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # === Supabase (Auth + DB) — needed in Stage 3+ ===
    SUPABASE_URL: str = Field(default="", description="Supabase project URL")
    SUPABASE_ANON_KEY: str = Field(default="", description="Public anon key (safe for frontend)")
    SUPABASE_SERVICE_KEY: str = Field(default="", description="Server-side service role key")

    # === AWS S3 — needed in Stage 3+ ===
    AWS_ACCESS_KEY_ID: str = Field(default="", description="IAM user access key")
    AWS_SECRET_ACCESS_KEY: str = Field(default="", description="IAM user secret key")
    AWS_REGION: str = "ap-south-1"
    S3_BUCKET_NAME: str = Field(default="lexai-documents", description="S3 bucket name")

    # === BM25 ===
    BM25_INDEX_PATH: str = Field(default="data/bm25_index.pkl", description="Path to persisted BM25 index")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# Global settings instance — import this everywhere
settings = Settings()
