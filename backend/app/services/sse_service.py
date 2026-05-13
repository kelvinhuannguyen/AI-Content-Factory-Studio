"""SSE (Server-Sent Events) via Redis pub/sub.

Publishers (Celery tasks) call `publish_event(project_id, event)`.
FastAPI endpoint subscribes and streams events to the browser.
"""
import asyncio
import json
import logging
from typing import AsyncGenerator

from ..redis_client import get_redis

logger = logging.getLogger(__name__)


def _channel(project_id: str) -> str:
    return f"sse:project:{project_id}"


async def publish_event(project_id: str, event: dict) -> None:
    """Publish a JSON event to all SSE subscribers of the project."""
    redis = await get_redis()
    await redis.publish(_channel(project_id), json.dumps(event))


async def stream_events(project_id: str) -> AsyncGenerator[str, None]:
    """Yield SSE-formatted strings for a FastAPI StreamingResponse."""
    redis = await get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(_channel(project_id))
    logger.info("SSE stream opened for project %s", project_id)

    try:
        # keepalive every 20s so proxies don't close the connection
        keepalive_interval = 20
        last_keepalive = asyncio.get_event_loop().time()

        while True:
            now = asyncio.get_event_loop().time()
            if now - last_keepalive >= keepalive_interval:
                yield ": keepalive\n\n"
                last_keepalive = now

            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message["type"] == "message":
                data = message["data"]
                yield f"data: {data}\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        await pubsub.unsubscribe(_channel(project_id))
        await pubsub.close()
        logger.info("SSE stream closed for project %s", project_id)
