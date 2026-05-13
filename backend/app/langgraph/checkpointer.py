"""LangGraph Redis checkpointer — async, using Upstash Redis.

One LangGraph thread = one project (thread_id == project_id).
Graph state is persisted in Redis so interrupt/resume survives server restarts.
"""
from __future__ import annotations
import ssl
from functools import lru_cache
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from ..config import get_settings


def _get_redis_url() -> str:
    settings = get_settings()
    return settings.redis_url


def get_thread_config(project_id: str) -> dict:
    """Return the LangGraph config dict for a given project thread."""
    return {"configurable": {"thread_id": project_id}}


_checkpointer: AsyncRedisSaver | None = None


async def get_checkpointer() -> AsyncRedisSaver:
    """Return a singleton AsyncRedisSaver, setup on first call."""
    global _checkpointer
    if _checkpointer is None:
        redis_url = _get_redis_url()
        connection_args: dict = {}
        if redis_url.startswith("rediss://"):
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            connection_args["ssl"] = ssl_ctx
        _checkpointer = AsyncRedisSaver(
            redis_url=redis_url,
            connection_args=connection_args,
        )
        await _checkpointer.asetup()
    return _checkpointer
