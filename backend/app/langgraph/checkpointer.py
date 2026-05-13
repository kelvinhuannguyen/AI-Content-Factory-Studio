"""LangGraph PostgreSQL checkpointer — dùng Neon DB thay vì Redis.

Lý do: langgraph-checkpoint-redis 0.4.x yêu cầu RediSearch (FT._LIST)
mà Upstash Redis không hỗ trợ. PostgreSQL checkpointer hoạt động với
Neon DB sẵn có, không cần module bổ sung.
"""
from __future__ import annotations
import logging
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from ..config import get_settings

logger = logging.getLogger(__name__)

_checkpointer: AsyncPostgresSaver | None = None


def get_thread_config(project_id: str) -> dict:
    """Return the LangGraph config dict for a given project thread."""
    return {"configurable": {"thread_id": project_id}}


async def get_checkpointer() -> AsyncPostgresSaver:
    """Return a singleton AsyncPostgresSaver, setup on first call."""
    global _checkpointer
    if _checkpointer is None:
        settings = get_settings()
        # AsyncPostgresSaver cần URL dạng postgresql:// (không phải asyncpg)
        db_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        _checkpointer = await AsyncPostgresSaver.from_conn_string(db_url)
        await _checkpointer.setup()
        logger.info("LangGraph PostgreSQL checkpointer initialized")
    return _checkpointer
