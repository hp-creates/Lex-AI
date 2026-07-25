"""
Supabase Service — Postgres operations for user document metadata.

Handles:
  - Inserting document records after upload
  - Fetching a user's document list
  - Deleting a document record

Uses the service-role key (bypasses RLS for trusted server-side ops).
Row Level Security is enforced at the Supabase level via policies.
"""

from supabase import create_client, Client
from app.config import settings

TABLE = "user_documents"


def _client() -> Client:
    """Create a fresh Supabase client using the service key."""
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)


def insert_document(
    user_id: str,
    doc_id: str,
    filename: str,
    file_type: str,
    chunk_count: int,
    total_chars: int,
    source_name: str = "",
) -> dict:
    """
    Insert a new document record into the user_documents table.
    Called after a successful upload + Qdrant upsert.
    """
    record = {
        "doc_id": doc_id,
        "user_id": user_id,
        "filename": filename,
        "file_type": file_type,
        "chunk_count": chunk_count,
        "total_chars": total_chars,
        "source_name": source_name or filename,
    }
    result = _client().table(TABLE).insert(record).execute()
    return result.data[0] if result.data else record


def get_user_documents(user_id: str) -> list[dict]:
    """
    Fetch all documents belonging to a user, newest first.
    """
    result = (
        _client()
        .table(TABLE)
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


def delete_document(doc_id: str, user_id: str) -> bool:
    """
    Delete a document record. Checks user_id ownership to prevent unauthorized deletes.
    Returns True if a row was deleted, False if not found.
    """
    result = (
        _client()
        .table(TABLE)
        .delete()
        .eq("doc_id", doc_id)
        .eq("user_id", user_id)
        .execute()
    )
    return len(result.data) > 0
