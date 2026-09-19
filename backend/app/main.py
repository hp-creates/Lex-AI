"""
LexAI — FastAPI Application Entry Point

Initializes the app, configures CORS, and registers all routers.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import health, query, upload, documents, chat
from app.services.vector_store import vector_store
from app.services.bm25_search import bm25_index
from app.services.embedder import embedder
from app.graph.workflow import get_rag_graph
import os

# ==========================================
# LangSmith Tracing
# ==========================================
if settings.LANGCHAIN_TRACING_V2.lower() == "true":
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_ENDPOINT"] = settings.LANGCHAIN_ENDPOINT
    os.environ["LANGCHAIN_API_KEY"] = settings.LANGCHAIN_API_KEY
    os.environ["LANGCHAIN_PROJECT"] = settings.LANGCHAIN_PROJECT
# ==========================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup/shutdown lifecycle.
    - Startup: initialize services (embedder, Qdrant, BM25) — added in later stages
    - Shutdown: cleanup connections
    """
    # === STARTUP ===
    print(f"[START] {settings.APP_NAME} v{settings.APP_VERSION} [{settings.ENVIRONMENT}]")

    # Initialize Qdrant
    vector_store.init_client()
    vector_store.create_collections(vector_size=1024)  # Jina v3 dimensions

    # Load BM25 index from disk (if exists)
    bm25_index.load()

    # Load embedding model (heavy -- ~800MB on first run)
    # This blocks startup but ensures the model is ready before serving requests
    print("[EMBEDDER] Loading model (this may take a minute)...")
    embedder.load()

    # Build and warm up the LangGraph pipeline (after all services are ready)
    print("[LANGGRAPH] Building RAG graph...")
    get_rag_graph()
    print("[LANGGRAPH] RAG graph ready.")

    yield  # App runs here

    # === SHUTDOWN ===
    print(f"[STOP] {settings.APP_NAME}")


# Create the FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    description="Indian Legal Rights Intelligence Platform — RAG-powered legal assistant",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# CORS — allow frontend to call the API
# In production, FRONTEND_ORIGIN is set to the deployed frontend URL.
# allow_origin_regex covers all *.onrender.com subdomains for Render deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_ORIGIN,
        "http://localhost:5173",   # Vite dev server
        "http://localhost:3000",   # Fallback
    ],
    allow_origin_regex=r"https://.*\.onrender\.com",  # Render deployment
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Register routers
app.include_router(health.router, prefix="/api/v1")
app.include_router(query.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(upload.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")


@app.get("/", tags=["root"])
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs",
        "health": "/api/v1/health",
    }

