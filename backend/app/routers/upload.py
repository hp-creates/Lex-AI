"""
Upload Router -- POST /upload endpoint.

Handles user document uploads:
1. Validate JWT -> extract user_id
2. Accept file (PDF, image, text) via multipart form
3. Extract text via doc_loader (PyMuPDF + OCR fallback)
4. Chunk via semantic chunker
5. Embed via Jina v3
6. Upsert to Qdrant (user_documents collection) + BM25 index
7. Save metadata to Supabase Postgres (user_documents table)

Returns: chunk count, doc_id, and processing stats.
"""

import uuid
import time

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from pydantic import BaseModel

from app.dependencies import get_current_user
from app.services.doc_loader import load_document, detect_file_type
from app.services.chunker import chunk_document
from app.services.embedder import embedder
from app.services.vector_store import vector_store
from app.services.bm25_search import bm25_index
from app.services.supabase_service import insert_document
from app.config import settings

router = APIRouter(tags=["upload"])


class UploadResponse(BaseModel):
    """Response body for POST /upload."""
    doc_id: str
    filename: str
    file_type: str
    chunk_count: int
    total_chars: int
    processing_time_s: float
    message: str


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    source_name: str = Form(default="", description="Optional display name for the document"),
    user_id: str = Depends(get_current_user),
):
    """
    Upload a document for RAG processing.

    Supports: PDF, PNG, JPG, TXT, MD
    Max size: 10MB (enforced by nginx/uvicorn in production)
    Requires: Authorization: Bearer <supabase_jwt>
    """
    start_time = time.time()

    # Validate file type
    filename = file.filename or "unknown"
    file_type = detect_file_type(filename)

    if file_type == "unsupported":
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: '{filename}'. Supported: PDF, PNG, JPG, TXT, MD"
        )

    # Read file bytes
    file_bytes = await file.read()
    if len(file_bytes) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=400, detail="File too large. Maximum: 10MB")

    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file uploaded")

    # Generate document ID
    doc_id = str(uuid.uuid4())
    display_name = source_name or filename

    # Step 1: Extract text
    try:
        text = load_document(
            filename=filename,
            file_bytes=file_bytes,
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to extract text: {str(e)[:200]}")

    if not text or text.startswith("<!-- No text") or text.startswith("<!-- Empty"):
        raise HTTPException(status_code=422, detail="No text could be extracted from this file")

    # Step 2: Chunk
    chunks = chunk_document(
        text=text,
        source=display_name,
        doc_id=doc_id,
        user_id=user_id,
        collection="user_documents",
    )

    if not chunks:
        raise HTTPException(status_code=422, detail="Document produced no chunks after splitting")

    # Step 3: Embed
    if not embedder.is_loaded:
        raise HTTPException(
            status_code=503,
            detail="Embedding model not loaded yet. Server is still starting up. Try again in a moment."
        )

    chunk_texts = [c["text"] for c in chunks]
    embeddings = embedder.embed_documents(chunk_texts)

    # Step 4: Upsert to Qdrant (user_documents collection)
    vector_store.upsert_chunks(
        collection=settings.QDRANT_USER_COLLECTION,
        chunks=chunks,
        embeddings=embeddings,
    )

    # Step 5: Add to BM25 index
    bm25_index.add_documents(chunks)

    # Step 6: Save metadata to Supabase Postgres
    processing_time = time.time() - start_time
    total_chars = sum(len(c["text"]) for c in chunks)

    try:
        insert_document(
            user_id=user_id,
            doc_id=doc_id,
            filename=filename,
            file_type=file_type,
            chunk_count=len(chunks),
            total_chars=total_chars,
            source_name=display_name,
        )
    except Exception as e:
        # Postgres insert failed — log but don't fail the upload
        # Qdrant already has the vectors; user can still query
        print(f"[UPLOAD] WARNING: Postgres metadata insert failed: {e}")

    print(f"[UPLOAD] {filename} -> {len(chunks)} chunks, {total_chars} chars, {processing_time:.1f}s (user: {user_id[:8]}...)")

    return UploadResponse(
        doc_id=doc_id,
        filename=filename,
        file_type=file_type,
        chunk_count=len(chunks),
        total_chars=total_chars,
        processing_time_s=round(processing_time, 2),
        message=f"Document '{display_name}' processed successfully.",
    )
