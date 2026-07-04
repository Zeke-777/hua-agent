"""Chat and session routes."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

from ..auth import get_current_user
from ..db import get_latest_session, list_sessions, verify_session_ownership
from ..schemas import ChatRequest, ChatResponse, SessionsResponse
from ..services.research import run_stage2

router = APIRouter(tags=["chat"])


@router.get("/api/sessions", response_model=SessionsResponse)
async def api_sessions(request: Request, username: str = Depends(get_current_user)):
    meta_conn = request.app.state.meta_conn
    sessions = await asyncio.to_thread(list_sessions, meta_conn, username)
    return SessionsResponse(ok=True, sessions=sessions)


@router.post("/api/chat", response_model=ChatResponse)
async def api_chat(body: ChatRequest, request: Request, username: str = Depends(get_current_user)):
    meta_conn = request.app.state.meta_conn
    stage2 = request.app.state.stage2

    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message 不能为空")

    async with request.app.state.active_sessions_lock:
        current_thread = body.session_id or request.app.state.active_sessions.get(username)
    if current_thread is None:
        current_thread = await asyncio.to_thread(get_latest_session, meta_conn, username)
    if current_thread is None:
        raise HTTPException(status_code=400, detail="没有活跃会话，请先输入花卉名称开始研究")

    owns = await asyncio.to_thread(
        verify_session_ownership, meta_conn, username, current_thread
    )
    if not owns:
        raise HTTPException(status_code=403, detail="无权访问该会话")

    reply = await run_stage2(message, current_thread, stage2, meta_conn)
    return ChatResponse(ok=True, stage=2, reply=reply)
