"""FastAPI application factory."""

import asyncio
import logging
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .db import init_meta_db
from .middleware import CSPMiddleware, RequestLoggingMiddleware

_logger = logging.getLogger("hua_agent")
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _init_resources(app: FastAPI, settings: Settings):
    """Initialize all runtime resources on app.state."""
    from langchain_openai import ChatOpenAI
    from langchain_tavily import TavilySearch
    from langgraph.checkpoint.sqlite import SqliteSaver
    from cachetools import TTLCache

    from .workflows.stage1 import create_stage1_workflow
    from .workflows.stage2 import create_stage2_agent

    model = ChatOpenAI(
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com/v1",
        api_key=settings.deepseek_api_key,
        temperature=0,
        extra_body={"thinking": {"type": "disabled"}},
    )
    tavily_tool = TavilySearch(max_results=5, tavily_api_key=settings.tavily_api_key)

    usersdata_path = os.path.join(_PROJECT_ROOT, "usersdata")
    os.makedirs(usersdata_path, exist_ok=True)

    ckpt_conn = sqlite3.connect(
        os.path.join(usersdata_path, "agent_memory.db"), check_same_thread=False
    )
    checkpointer = SqliteSaver(ckpt_conn)

    meta_conn = sqlite3.connect(
        os.path.join(usersdata_path, "meta.db"), check_same_thread=False
    )
    init_meta_db(meta_conn)

    stage1 = create_stage1_workflow(model, tavily_tool, checkpointer)
    stage2 = create_stage2_agent(model, tavily_tool, checkpointer)

    from .obs_client import init_obs
    if settings.ak and settings.sk:
        init_obs(settings.ak, settings.sk, settings.endpoint, settings.bucket_name)

    app.state.meta_conn = meta_conn
    app.state.stage1 = stage1
    app.state.stage2 = stage2
    app.state.active_sessions = TTLCache(maxsize=10000, ttl=3600)
    app.state.active_sessions_lock = asyncio.Lock()
    app.state.executor = ThreadPoolExecutor(max_workers=4)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = app.state.settings
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _init_resources, app, settings)
    yield
    app.state.executor.shutdown(wait=True)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    if settings is None:
        settings = Settings()

    app = FastAPI(title="花卉研究 Agent API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(CSPMiddleware)
    app.add_middleware(RequestLoggingMiddleware)

    app.mount("/static", StaticFiles(directory="static"), name="static")

    from .routes.auth import router as auth_router
    from .routes.research import router as research_router
    from .routes.chat import router as chat_router
    app.include_router(auth_router)
    app.include_router(research_router)
    app.include_router(chat_router)

    @app.get("/")
    async def root():
        return FileResponse(os.path.join(_PROJECT_ROOT, "static", "dist", "index.html"))

    from .spa import create_spa_fallback
    app.get("/{path:path}")(create_spa_fallback())

    return app
