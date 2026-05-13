"""LangGraph in-memory checkpointer.

MemorySaver không cần Redis hay PostgreSQL — state tồn tại trong process.
Đủ dùng cho single-instance Railway deployment.
"""
from __future__ import annotations
import logging
from langgraph.checkpoint.memory import MemorySaver

logger = logging.getLogger(__name__)

_checkpointer: MemorySaver | None = None


def get_thread_config(project_id: str) -> dict:
    return {"configurable": {"thread_id": project_id}}


async def get_checkpointer() -> MemorySaver:
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = MemorySaver()
        logger.info("LangGraph MemorySaver checkpointer initialized")
    return _checkpointer
