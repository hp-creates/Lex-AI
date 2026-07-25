"""
Health check router — liveness probe for Docker/EC2 health checks.
No auth required. Reports status of core services.
"""

from fastapi import APIRouter
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse

from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """
    Liveness probe. Returns status of:
    - API server
    - Qdrant connection
    """
    qdrant_status = "disconnected"

    try:
        client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT, timeout=5)
        # Simple connectivity check — list collections
        client.get_collections()
        qdrant_status = "connected"
    except (UnexpectedResponse, Exception) as e:
        qdrant_status = f"error: {str(e)[:100]}"

    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "qdrant": qdrant_status,
    }
