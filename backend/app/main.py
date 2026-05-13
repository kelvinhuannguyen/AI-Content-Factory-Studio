from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api.v1.router import router as v1_router
from .database import init_db
from .redis_client import get_redis, close_redis
from .config import get_settings

settings = get_settings()


import logging
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — graceful: server starts even if DB/Redis unavailable
    try:
        await init_db()
        logger.info("Database connected and tables created")
    except Exception as e:
        logger.warning("Database not available (will retry on requests): %s", e)
    try:
        await get_redis()
        logger.info("Redis connected")
    except Exception as e:
        logger.warning("Redis not available: %s", e)
    yield
    # Shutdown
    try:
        await close_redis()
    except Exception:
        pass


app = FastAPI(
    title="AI Content Factory Studio",
    description="Nền tảng sản xuất video AI toàn diện",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "https://ai-content-factory-studio.vercel.app",
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "AI Content Factory Studio"}


@app.get("/api/v1/queue/stats")
async def queue_stats():
    return {"cpu_queue": 0, "gpu_queue": 0, "workers": 0}


@app.get("/api/v1/settings")
async def get_settings_endpoint():
    return {
        "kymaapi_configured":     bool(settings.kymaapi_key),
        "elevenlabs_configured":  bool(settings.elevenlabs_api_key),
        "suno_configured":        bool(settings.suno_api_key),
        "gmail_smtp_configured":  bool(settings.gmail_app_password),
        "telegram_configured":    bool(settings.telegram_bot_token),
        "r2_configured":          bool(settings.r2_access_key_id),
        "youtube_configured":     bool(settings.youtube_client_id),
    }


@app.post("/api/v1/test/email")
async def test_email():
    """Dev-only: send a test approval email to notification_email."""
    from .config import get_settings as _gs
    _gs.cache_clear()                       # pick up .env changes without restart
    fresh = _gs()

    from .services.notification_service import send_approval_request
    import importlib, app.services.notification_service as _ns
    # Reload to pick up fresh settings
    importlib.reload(_ns)

    token = await _ns.send_approval_request(
        project_id="00000000-0000-0000-0000-000000000001",
        project_title="[TEST] AI Content Factory",
        step="script_review",
        extra_info=f"SMTP: {bool(fresh.gmail_app_password)} | SA: {bool(fresh.gmail_service_account_json)}",
    )
    return {
        "sent_to": fresh.notification_email,
        "smtp_configured": bool(fresh.gmail_app_password),
        "password_length": len(fresh.gmail_app_password.replace(" ", "")),
        "token": token,
        "approve_url": f"{fresh.backend_url}/api/v1/approvals/{token}?action=approve",
        "reject_url":  f"{fresh.backend_url}/api/v1/approvals/{token}?action=reject",
    }
