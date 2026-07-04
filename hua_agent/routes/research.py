"""Research and upload routes."""

import asyncio

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from ..auth import get_current_user
from ..db import (
    get_or_create_flower_session,
    get_session_data,
    update_session_flower_info,
)
from ..image_utils import validate_upload
from ..schemas import ResearchRequest, ResearchResponse
from ..services.flower_id import identify_flower_from_url
from ..services.research import run_stage1

router = APIRouter(tags=["research"])


@router.post("/api/research", response_model=ResearchResponse)
async def api_research(body: ResearchRequest, request: Request, username: str = Depends(get_current_user)):
    meta_conn = request.app.state.meta_conn
    stage1 = request.app.state.stage1

    flower_name = body.flower_name.strip()
    if not flower_name:
        raise HTTPException(status_code=400, detail="flower_name 不能为空")

    sid, is_new = await asyncio.to_thread(
        get_or_create_flower_session, meta_conn, username, flower_name
    )
    async with request.app.state.active_sessions_lock:
        request.app.state.active_sessions[username] = sid

    if is_new:
        reply, report = await run_stage1(flower_name, sid, stage1, meta_conn)
        await asyncio.to_thread(update_session_flower_info, meta_conn, sid, report)
        return ResearchResponse(
            ok=True, stage=1, session_id=sid,
            flower_name=flower_name, flower_info=report, image_url=None,
        )
    else:
        image_url, flower_info = await asyncio.to_thread(
            get_session_data, meta_conn, sid
        )
        return ResearchResponse(
            ok=True, stage=1 if flower_info is None else 2,
            session_id=sid, flower_name=flower_name,
            flower_info=flower_info, image_url=image_url,
        )


async def _upload_and_research(request, file, flower_name, username):
    """Core upload logic: validate, upload to OBS, identify, run research."""
    meta_conn = request.app.state.meta_conn
    stage1 = request.app.state.stage1
    executor = request.app.state.executor

    body = await file.read()
    validate_upload(file.filename, file.content_type, body)

    from ..obs_client import upload_image

    loop = asyncio.get_running_loop()
    url = await loop.run_in_executor(
        executor, upload_image, body, file.filename, username
    )

    if not flower_name.strip():
        flower_name = await asyncio.to_thread(identify_flower_from_url, url)
    else:
        flower_name = flower_name.strip()

    sid, is_new = await asyncio.to_thread(
        get_or_create_flower_session, meta_conn, username, flower_name, image_url=url
    )
    async with request.app.state.active_sessions_lock:
        request.app.state.active_sessions[username] = sid

    if not is_new:
        img_url, flower_info = await asyncio.to_thread(get_session_data, meta_conn, sid)
        if flower_info is not None:
            return ResearchResponse(
                ok=True, stage=2, session_id=sid,
                flower_name=flower_name, flower_info=flower_info,
                image_url=img_url or url,
            )

    reply, report = await run_stage1(flower_name, sid, stage1, meta_conn)
    await asyncio.to_thread(update_session_flower_info, meta_conn, sid, report, image_url=url)
    return ResearchResponse(
        ok=True, stage=1, session_id=sid,
        flower_name=flower_name, flower_info=report, image_url=url,
    )


@router.post("/api/upload", response_model=ResearchResponse)
async def api_upload(
    request: Request,
    file: UploadFile = File(...),
    flower_name: str = Form(""),
    username: str = Depends(get_current_user),
):
    return await _upload_and_research(request, file, flower_name, username)
