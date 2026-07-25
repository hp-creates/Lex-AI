"""
Documents Router — GET /documents and DELETE /documents/{doc_id}.

Requires auth: Authorization: Bearer <supabase_jwt>

GET  /documents        -> list all documents for the current user (from Postgres)
DELETE /documents/{id} -> delete document from Postgres + Qdrant
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.dependencies import get_current_user
from app.services.supabase_service import get_user_documents, delete_document
from app.services.vector_store import vector_store
from app.services.bm25_search import bm25_index
from app.config import settings

router = APIRouter(tags=["documents"])


class DocumentRecord(BaseModel):
    """A single document record returned from Postgres."""
    doc_id: str
    filename: str
    file_type: str
    chunk_count: int
    total_chars: int
    source_name: str
    created_at: str


class DeleteResponse(BaseModel):
    doc_id: str
    message: str


@router.get("/documents", response_model=list[DocumentRecord])
async def list_documents(user_id: str = Depends(get_current_user)):
    """
    List all uploaded documents for the current user.
    Results are fetched from Supabase Postgres (lightweight metadata only).
    """
    try:
        docs = get_user_documents(user_id)
        return docs
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch documents: {str(e)[:200]}")


@router.delete("/documents/{doc_id}", response_model=DeleteResponse)
async def delete_user_document(
    doc_id: str,
    user_id: str = Depends(get_current_user),
):
    """
    Delete a user document:
    1. Remove metadata from Supabase Postgres
    2. Delete all vector points from Qdrant (filter by doc_id + user_id)
    """
    # 1. Delete from Postgres (validates ownership)
    deleted = delete_document(doc_id=doc_id, user_id=user_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Document '{doc_id}' not found or does not belong to you."
        )

    # 2. Delete all Qdrant points for this doc
    try:
        vector_store.delete_by_doc_id(
            collection=settings.QDRANT_USER_COLLECTION,
            doc_id=doc_id,
        )
    except Exception as e:
        # Qdrant deletion failed — log, but Postgres is already clean
        print(f"[DELETE] WARNING: Qdrant cleanup failed for doc {doc_id}: {e}")

    # 3. Remove from BM25 index
    try:
        bm25_index.remove_by_doc_id(doc_id)
        print(f"[DELETE] Removed doc {doc_id} from BM25 index")
    except Exception as e:
        print(f"[DELETE] WARNING: BM25 index cleanup failed for doc {doc_id}: {e}")

    print(f"[DELETE] doc_id={doc_id} removed for user={user_id[:8]}...")

    return DeleteResponse(
        doc_id=doc_id,
        message="Document deleted successfully.",
    )
