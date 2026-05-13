import redis.asyncio as aioredis
from .config import get_settings

settings = get_settings()

_redis_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis_pool
    if _redis_pool is None:
        # rediss:// = SSL (Upstash), redis:// = plain (local)
        use_ssl = settings.redis_url.startswith("rediss://")
        _redis_pool = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
            ssl_cert_reqs="none" if use_ssl else None,  # Upstash dùng self-signed cert
        )
    return _redis_pool


async def close_redis():
    global _redis_pool
    if _redis_pool:
        await _redis_pool.aclose()
        _redis_pool = None
