"""Authentication dependency for FastAPI routes."""

import asyncio

from fastapi import Header, HTTPException, Request


async def get_current_user(
    request: Request, authorization: str | None = Header(None)
) -> str:
    """FastAPI dependency: validates Bearer token and returns username."""
    if not authorization:
        raise HTTPException(status_code=401, detail="缺少 Authorization header")
    meta_conn = request.app.state.meta_conn

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="缺少或无效的 Authorization header")

    token = authorization[7:]
    # Defer import to avoid circular dependency at module load time
    from .db import verify_token

    username = await asyncio.to_thread(verify_token, meta_conn, token)
    if username is None:
        raise HTTPException(status_code=401, detail="token 无效或已过期")
    return username
