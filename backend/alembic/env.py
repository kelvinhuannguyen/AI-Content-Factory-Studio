import asyncio
import ssl
from logging.config import fileConfig
from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.database import Base
from app.models import *  # noqa: F401,F403 — register all models with metadata
from app.config import get_settings

config = context.config
settings = get_settings()

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Dùng pooled URL nếu có (Neon PgBouncer), fallback về database_url
_migration_url_raw = settings.database_url_pooled or settings.database_url

# Strip các params asyncpg không hỗ trợ
_migration_url = _migration_url_raw
for param in (
    "sslmode=require", "sslmode=prefer", "sslmode=allow", "sslmode=disable",
    "channel_binding=require", "channel_binding=prefer",
):
    _migration_url = _migration_url.replace(f"?{param}", "?").replace(f"&{param}", "")
_migration_url = _migration_url.rstrip("?&").replace("?&", "?")

# SSL auto-detect
_needs_ssl = any(kw in _migration_url_raw for kw in ("neon.tech", "sslmode=require", "sslmode=prefer"))
_connect_args: dict = {}
if _needs_ssl:
    _ssl_ctx = ssl.create_default_context()
    _connect_args["ssl"] = _ssl_ctx
if "-pooler." in _migration_url_raw:
    _connect_args["statement_cache_size"] = 0


def run_migrations_offline() -> None:
    context.configure(
        url=_migration_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(_migration_url, connect_args=_connect_args)
    async with engine.connect() as conn:
        await conn.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
