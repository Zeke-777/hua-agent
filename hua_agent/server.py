import asyncio
import os
import sqlite3
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .db import (
    create_token,
    delete_token,
    get_latest_session,
    get_or_create_flower_session,
    get_session_data,
    init_meta_db,
    list_sessions,
    login_user,
    register_user,
    update_last_active,
    update_session_flower_info,
    verify_token,
)
from .models import ChatRequest, ResearchResponse
from .stage1_workflow import create_stage1_workflow
from .stage2_agent import create_stage2_agent
from .obs_client import upload_image

load_dotenv()

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ============================================================================
# Global resources (initialized at startup)
# ============================================================================

model = None
tavily_tool = None
checkpointer = None
meta_conn = None
stage1 = None
stage2 = None

# Memory state
active_sessions: dict[str, str] = {}  # username -> current thread_id

# Thread pool for sync LangGraph calls (None = use default executor)
_EXECUTOR = None


def _init_resources():
    global model, tavily_tool, checkpointer, meta_conn, stage1, stage2
    from langchain_openai import ChatOpenAI
    from langchain_tavily import TavilySearch
    from langgraph.checkpoint.sqlite import SqliteSaver

    model = ChatOpenAI(
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com/v1",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        temperature=0,
        extra_body={"thinking": {"type": "disabled"}},
    )
    tavily_tool = TavilySearch(max_results=5)

    os.makedirs("usersdata", exist_ok=True)
    ckpt_conn = sqlite3.connect("usersdata/agent_memory.db", check_same_thread=False)
    checkpointer = SqliteSaver(ckpt_conn)

    meta_conn = sqlite3.connect("usersdata/meta.db", check_same_thread=False)
    init_meta_db(meta_conn)

    stage1 = create_stage1_workflow(model, tavily_tool, checkpointer)
    stage2 = create_stage2_agent(model, tavily_tool, checkpointer)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _init_resources()
    yield


app = FastAPI(title="花卉研究 Agent API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Pydantic schemas
# ============================================================================


class AuthRequest(BaseModel):
    username: str
    password: str


class ResearchRequest(BaseModel):
    flower_name: str


class OKResponse(BaseModel):
    ok: bool
    message: str = ""


class LoginResponse(BaseModel):
    ok: bool
    token: str = ""
    username: str = ""


class SessionsResponse(BaseModel):
    ok: bool
    sessions: list[dict] = []


class ChatResponse(BaseModel):
    ok: bool
    stage: int = 0
    reply: str = ""


# ============================================================================
# External API placeholder
# ============================================================================


def _identify_flower_from_url(image_url: str) -> str:
    import json as _json
    import urllib.request as _req

    body = _json.dumps({"image_url": image_url}).encode()
    rq = _req.Request(
        "http://127.0.0.1:8000/predict",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with _req.urlopen(rq, timeout=30) as resp:
            data = _json.loads(resp.read())
        return data["data"]["flower_name"]
    except Exception:
        raise HTTPException(status_code=501, detail="外部花卉识别接口暂不可用")


# ============================================================================
# Auth dependency
# ============================================================================


async def get_current_user(authorization: str = Header(...)) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="缺少或无效的 Authorization header")
    token = authorization[7:]
    username = await asyncio.to_thread(verify_token, meta_conn, token)
    if username is None:
        raise HTTPException(status_code=401, detail="token 无效或已过期")
    return username


# ============================================================================
# Helpers
# ============================================================================


def _extract_reply(result) -> str:
    if not isinstance(result, dict):
        return ""
    messages = result.get("messages", [])
    for msg in reversed(messages):
        cls_name = msg.__class__.__name__
        if cls_name == "AIMessage" and hasattr(msg, "content"):
            return msg.content
    return ""


async def _run_stage1(flower_name: str, thread_id: str) -> tuple[str, dict]:
    config = {"configurable": {"thread_id": thread_id}}
    result = await asyncio.to_thread(
        stage1.invoke,
        {"messages": [{"role": "user", "content": flower_name}]},
        config,
    )
    await asyncio.to_thread(update_last_active, meta_conn, thread_id)
    reply = _extract_reply(result)
    report = result.get("report", {})
    return reply, report


async def _run_stage2(message: str, thread_id: str) -> str:
    config = {"configurable": {"thread_id": thread_id}}
    result = await asyncio.to_thread(
        stage2.invoke,
        {"messages": [{"role": "user", "content": message}]},
        config,
    )
    await asyncio.to_thread(update_last_active, meta_conn, thread_id)
    return _extract_reply(result)


# ============================================================================
# Routes
# ============================================================================


@app.get("/")
async def root():
    return FileResponse(os.path.join(_PROJECT_ROOT, "static", "dist", "index.html"))


@app.post("/api/auth/register", response_model=OKResponse)
async def api_register(body: AuthRequest):
    ok, msg = await asyncio.to_thread(
        register_user, meta_conn, body.username, body.password
    )
    if not ok:
        raise HTTPException(status_code=409, detail=msg)
    return OKResponse(ok=True, message=msg)


@app.post("/api/auth/login", response_model=LoginResponse)
async def api_login(body: AuthRequest):
    username, msg = await asyncio.to_thread(
        login_user, meta_conn, body.username, body.password
    )
    if username is None:
        raise HTTPException(status_code=401, detail=msg)
    token = await asyncio.to_thread(create_token, meta_conn, username)
    return LoginResponse(ok=True, token=token, username=username)


@app.get("/api/sessions", response_model=SessionsResponse)
async def api_sessions(username: str = Depends(get_current_user)):
    sessions = await asyncio.to_thread(list_sessions, meta_conn, username)
    return SessionsResponse(ok=True, sessions=sessions)


@app.post("/api/research", response_model=ResearchResponse)
async def api_research(body: ResearchRequest, username: str = Depends(get_current_user)):
    flower_name = body.flower_name.strip()
    if not flower_name:
        raise HTTPException(status_code=400, detail="flower_name 不能为空")

    sid, is_new = await asyncio.to_thread(
        get_or_create_flower_session, meta_conn, username, flower_name
    )
    active_sessions[username] = sid

    if is_new:
        reply, report = await _run_stage1(flower_name, sid)
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


@app.post("/api/chat", response_model=ChatResponse)
async def api_chat(body: ChatRequest, username: str = Depends(get_current_user)):
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message 不能为空")

    # Resolve active session: explicit session_id > memory > latest in DB
    current_thread = body.session_id or active_sessions.get(username)
    if current_thread is None:
        current_thread = await asyncio.to_thread(get_latest_session, meta_conn, username)
    if current_thread is None:
        raise HTTPException(status_code=400, detail="没有活跃会话，请先输入花卉名称开始研究")

    # Verify session ownership
    prefix = f"{username}:"
    if not current_thread.startswith(prefix):
        raise HTTPException(status_code=403, detail="无权访问该会话")

    reply = await _run_stage2(message, current_thread)
    return ChatResponse(ok=True, stage=2, reply=reply)


@app.post("/api/auth/logout", response_model=OKResponse)
async def api_logout(
    authorization: str = Header(...),
    username: str = Depends(get_current_user),
):
    if authorization.startswith("Bearer "):
        token = authorization[7:]
        await asyncio.to_thread(delete_token, meta_conn, token)
    return OKResponse(ok=True, message="已登出")


ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB


@app.post("/api/upload", response_model=ResearchResponse)
async def api_upload(
    file: UploadFile = File(...),
    flower_name: str = Form(""),
    username: str = Depends(get_current_user),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名为空")
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext}")
    body = await file.read()
    if len(body) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="文件大小超过 10MB 限制")

    loop = asyncio.get_running_loop()
    url = await loop.run_in_executor(
        _EXECUTOR, upload_image, body, file.filename, username
    )

    # Identify flower name: use provided name or call external API
    if not flower_name.strip():
        flower_name = await asyncio.to_thread(_identify_flower_from_url, url)
    else:
        flower_name = flower_name.strip()

    # Create/load session and research
    sid, is_new = await asyncio.to_thread(
        get_or_create_flower_session, meta_conn, username, flower_name, image_url=url
    )
    active_sessions[username] = sid

    if is_new:
        reply, report = await _run_stage1(flower_name, sid)
        await asyncio.to_thread(update_session_flower_info, meta_conn, sid, report, image_url=url)
        return ResearchResponse(
            ok=True, stage=1, session_id=sid,
            flower_name=flower_name, flower_info=report, image_url=url,
        )
    else:
        image_url, flower_info = await asyncio.to_thread(
            get_session_data, meta_conn, sid
        )
        return ResearchResponse(
            ok=True, stage=2, session_id=sid,
            flower_name=flower_name, flower_info=flower_info,
            image_url=image_url or url,
        )


# Catch-all for SPA static files (must be after all /api/* routes)
@app.get("/{path:path}")
async def spa_fallback(path: str):
    if ".." in path:
        raise HTTPException(status_code=404, detail="Not Found")
    import stat as _stat
    full = os.path.join(_PROJECT_ROOT, "static", "dist", path)
    try:
        _stat.S_IFMT(os.stat(full).st_mode)
        return FileResponse(full)
    except (FileNotFoundError, NotADirectoryError):
        pass
    return FileResponse(os.path.join(_PROJECT_ROOT, "static", "dist", "index.html"))


def main():
    import uvicorn
    uvicorn.run("hua_agent.server:app", host="0.0.0.0", port=5000, reload=True)


if __name__ == "__main__":
    main()
