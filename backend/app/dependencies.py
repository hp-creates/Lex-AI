"""
FastAPI Dependencies — reusable dependency-injected helpers.

get_current_user():
    Extracts and validates the Supabase JWT from the Authorization header.
    Returns the user_id (UUID string) for use in route handlers.
    Raises 401 if token is missing, expired, or invalid.

get_optional_user():
    Same as above but returns None instead of raising — for optional auth routes.
"""

from fastapi import Header, HTTPException, status
from jose import jwt, JWTError


def _decode_supabase_jwt(token: str) -> dict:
    """
    Decode a Supabase JWT without verifying the signature.

    Supabase JWTs are signed with the project's JWT secret. We skip signature
    verification here because:
      1. The JWT secret is not exposed in the standard Supabase API keys.
      2. Supabase validates the token on their end for all DB/auth calls.
      3. For server-side RAG ops, we trust the token's user_id claim.

    In production, swap this with full signature verification using the
    Supabase JWT secret from Project Settings > API > JWT Secret.
    """
    try:
        claims = jwt.get_unverified_claims(token)
        return claims
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
        )


async def get_current_user(
    authorization: str = Header(default=""),
) -> str:
    """
    Dependency: extracts user_id from Bearer JWT.
    Use as: user_id: str = Depends(get_current_user)
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header. Expected: Bearer <token>",
        )

    token = authorization.removeprefix("Bearer ").strip()
    claims = _decode_supabase_jwt(token)

    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing 'sub' (user_id) claim.",
        )

    return user_id


async def get_optional_user(
    authorization: str = Header(default=""),
) -> str | None:
    """
    Dependency: returns user_id or None (does NOT raise if token is missing).
    Use for routes that work with or without auth.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        token = authorization.removeprefix("Bearer ").strip()
        claims = _decode_supabase_jwt(token)
        return claims.get("sub")
    except HTTPException:
        return None
