"""LangGraph PostgreSQL checkpointer — dùng psycopg + connection pool."""
from __future__ import annotations
import logging
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from ..config import get_settings

logger = logging.getLogger(__name__)

_checkpointer: AsyncPostgresSaver | None = None
_pool: AsyncConnectionPool | None = None


def get_thread_config(project_id: str) -> dict:
    return {"configurable": {"thread_id": project_id}}


def _build_conn_string() -> str:
    settings = get_settings()
    url = settings.database_url
    # psycopg dùng postgresql://, không phải postgresql+asyncpg://
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    # Neon yêu cầu SSL
    if "sslmode" not in url:
        url += "?sslmode=require"
    return url


async def get_checkpointer() -> AsyncPostgresSaver:
    """Return singleton AsyncPostgresSaver backed by a connection pool."""
    global _checkpointer, _pool
    if _checkpointer is None:
        conn_string = _build_conn_string()
        _pool = AsyncConnectionPool(
            conninfo=conn_string,
            max_size=5,
            open=False,
        )
        await _pool.open()
        _checkpointer = AsyncPostgresSaver(_pool)
        await _checkpointer.setup()
        logger.info("LangGraph PostgreSQL checkpointer initialized with pool")
    return _checkpointer
