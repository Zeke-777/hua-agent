"""Authentication routes: register, login, logout."""

import asyncio

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from ..auth import get_current_user
from ..db import create_token, delete_token, login_user, register_user
from ..schemas import AuthRequest, LoginResponse, OKResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=OKResponse)
async def api_register(body: AuthRequest, request: Request):
    meta_conn = request.app.state.meta_conn
    ok, msg = await asyncio.to_thread(
        register_user, meta_conn, body.username, body.password
    )
    if not ok:
        raise HTTPException(status_code=409, detail=msg)
    return OKResponse(ok=True, message=msg)


@router.post("/login", response_model=LoginResponse)
async def api_login(body: AuthRequest, request: Request):
    meta_conn = request.app.state.meta_conn
    username, msg = await asyncio.to_thread(
        login_user, meta_conn, body.username, body.password
    )
    if username is None:
        raise HTTPException(status_code=401, detail=msg)
    token = await asyncio.to_thread(create_token, meta_conn, username)
    return LoginResponse(ok=True, token=token, username=username)


@router.post("/logout", response_model=OKResponse)
async def api_logout(
    request: Request,
    authorization: str = Header(...),
    username: str = Depends(get_current_user),
):
    meta_conn = request.app.state.meta_conn
    if authorization.startswith("Bearer "):
        token = authorization[7:]
        await asyncio.to_thread(delete_token, meta_conn, token)
    async with request.app.state.active_sessions_lock:
        request.app.state.active_sessions.pop(username, None)
    return OKResponse(ok=True, message="已登出")
