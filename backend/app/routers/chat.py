"""
Chat Router -- Endpoints for managing chat sessions and messages.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import get_current_user
from app.services.supabase_service import (
    create_chat_session,
    get_chat_sessions,
    get_chat_messages,
    update_chat_session_title,
    delete_chat_session,
)

router = APIRouter(tags=["chat"])


class CreateSessionRequest(BaseModel):
    title: str = "New Chat"


class UpdateSessionRequest(BaseModel):
    title: str


class SessionResponse(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: str


@router.post("/sessions", response_model=dict)
async def create_session(
    request: CreateSessionRequest,
    user_id: str = Depends(get_current_user),
):
    """Create a new chat session."""
    try:
        session_id = create_chat_session(user_id=user_id, title=request.title)
        return {"session_id": session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create session: {str(e)}")


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(user_id: str = Depends(get_current_user)):
    """List all chat sessions for the current user."""
    try:
        sessions = get_chat_sessions(user_id=user_id)
        return sessions
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch sessions: {str(e)}")


@router.patch("/sessions/{session_id}", response_model=dict)
async def rename_session(
    session_id: str,
    request: UpdateSessionRequest,
    user_id: str = Depends(get_current_user),
):
    """Rename a chat session."""
    try:
        updated = update_chat_session_title(session_id=session_id, user_id=user_id, title=request.title)
        if not updated:
            raise HTTPException(status_code=404, detail="Session not found or not owned by user")
        return {"status": "success", "session": updated}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rename session: {str(e)}")


@router.delete("/sessions/{session_id}", response_model=dict)
async def remove_session(
    session_id: str,
    user_id: str = Depends(get_current_user),
):
    """Delete a chat session and all its messages."""
    try:
        deleted = delete_chat_session(session_id=session_id, user_id=user_id)
        return {"status": "success", "deleted": deleted}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete session: {str(e)}")


@router.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    session_id: str,
    user_id: str = Depends(get_current_user),
):
    """
    List all messages in a specific session.
    RLS policies in Supabase ensure users can only read their own session's messages.
    """
    try:
        messages = get_chat_messages(session_id=session_id)
        return messages
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch messages: {str(e)}")
