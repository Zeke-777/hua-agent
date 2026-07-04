"""Research service helpers — stage1/stage2 invocations."""

import asyncio

from ..db import update_last_active


def _extract_reply(result) -> str:
    """Extract the last AI message from a LangGraph result."""
    if not isinstance(result, dict):
        return ""
    messages = result.get("messages", [])
    for msg in reversed(messages):
        cls_name = msg.__class__.__name__
        if cls_name == "AIMessage" and hasattr(msg, "content"):
            return msg.content
    return ""


async def run_stage1(flower_name: str, thread_id: str, stage1, meta_conn) -> tuple[str, dict]:
    """Execute Stage 1 workflow: search → extract → report."""
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


async def run_stage2(message: str, thread_id: str, stage2, meta_conn) -> str:
    """Execute Stage 2 agent: multi-turn chat with tools."""
    config = {"configurable": {"thread_id": thread_id}}
    result = await asyncio.to_thread(
        stage2.invoke,
        {"messages": [{"role": "user", "content": message}]},
        config,
    )
    await asyncio.to_thread(update_last_active, meta_conn, thread_id)
    return _extract_reply(result)
