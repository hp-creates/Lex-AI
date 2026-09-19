"""
Health check router — liveness probe for Docker/EC2 health checks.
No auth required. Reports status of core services.
"""

from fastapi import APIRouter

from app.config import settings
from app.services.vector_store import vector_store

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
        vector_store.client.get_collections()
        qdrant_status = "connected"
    except Exception as e:
        qdrant_status = f"error: {str(e)[:100]}"

    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "qdrant": qdrant_status,
    }

