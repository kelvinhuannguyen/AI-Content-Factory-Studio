import ssl
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from .config import get_settings

settings = get_settings()

# SSL auto-detect: bật khi URL có "neon.tech", "sslmode=require", hoặc host cloud khác
_needs_ssl = any(kw in settings.database_url for kw in (
    "neon.tech", "sslmode=require", "sslmode=prefer",
    "supabase.co", "render.com", "railway.app",
))

_connect_args: dict = {}
if _needs_ssl:
    _ssl_ctx = ssl.create_default_context()
    _connect_args["ssl"] = _ssl_ctx

# PgBouncer (Neon pooler) cần tắt prepared statement cache
if "-pooler." in settings.database_url:
    _connect_args["statement_cache_size"] = 0

# Strip các params asyncpg không hỗ trợ ra khỏi URL
_db_url = settings.database_url
for param in (
    "sslmode=require", "sslmode=prefer", "sslmode=allow", "sslmode=disable",
    "channel_binding=require", "channel_binding=prefer",
):
    _db_url = _db_url.replace(f"?{param}", "?").replace(f"&{param}", "")
_db_url = _db_url.rstrip("?&").replace("?&", "?")

engine = create_async_engine(
    _db_url,
    connect_args=_connect_args,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,        # Giảm xuống cho Neon (auto-suspend giữa requests)
    max_overflow=10,
    pool_recycle=300,   # Recycle connections mỗi 5 phút — tránh idle timeout
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Tạo tables nếu chưa có (dùng cho dev local, production dùng alembic upgrade head)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
