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


# ==============================================================================
# Chat History Functions
# ==============================================================================

def create_chat_session(user_id: str, title: str = "New Chat") -> str:
    """Create a new chat session and return its ID."""
    record = {
        "user_id": user_id,
        "title": title,
    }
    result = _client().table("chat_sessions").insert(record).execute()
    return result.data[0]["id"]


def get_chat_sessions(user_id: str) -> list[dict]:
    """Get all chat sessions for a user, newest first."""
    result = (
        _client()
        .table("chat_sessions")
        .select("id, title, created_at, updated_at")
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .execute()
    )
    return result.data or []


def add_chat_message(session_id: str, role: str, content: str) -> dict:
    """Add a message to a chat session."""
    if role not in ("user", "assistant", "system"):
        raise ValueError(f"Invalid role: {role}")
        
    record = {
        "session_id": session_id,
        "role": role,
        "content": content,
    }
    result = _client().table("chat_messages").insert(record).execute()
    
    # Update the session's updated_at timestamp
    try:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        _client().table("chat_sessions").update({"updated_at": now}).eq("id", session_id).execute()
    except Exception as e:
        print(f"[DB] Error updating session timestamp: {e}")
        
    return result.data[0] if result.data else record


def get_chat_messages(session_id: str, limit: int = None) -> list[dict]:
    """
    Get messages for a session, oldest first (chronological).
    If limit is provided, gets the LAST `limit` messages (e.g. limit=6 gets last 3 turns).
    """
    query = (
        _client()
        .table("chat_messages")
        .select("id, role, content, created_at")
        .eq("session_id", session_id)
        .order("created_at", desc=False)  # Chronological order
    )
    
    result = query.execute()
    messages = result.data or []
    
    if limit and len(messages) > limit:
        # Return only the last `limit` messages
        return messages[-limit:]
        
    return messages


def update_chat_session_title(session_id: str, user_id: str, title: str) -> dict:
    """Update the title of a chat session."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    result = (
        _client()
        .table("chat_sessions")
        .update({"title": title, "updated_at": now})
        .eq("id", session_id)
        .eq("user_id", user_id)
        .execute()
    )
    return result.data[0] if result.data else {}


def delete_chat_session(session_id: str, user_id: str) -> bool:
    """Delete a chat session and all associated messages."""
    # Delete messages first in case CASCADE is not set on the foreign key
    _client().table("chat_messages").delete().eq("session_id", session_id).execute()
    result = (
        _client()
        .table("chat_sessions")
        .delete()
        .eq("id", session_id)
        .eq("user_id", user_id)
        .execute()
    )
    return bool(result.data)

