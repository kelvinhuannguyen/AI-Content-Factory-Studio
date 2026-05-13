import ssl
from celery import Celery
from ..config import get_settings

settings = get_settings()

celery_app = Celery(
    "aicfs",
    broker=settings.redis_url,
    backend=settings.redis_url.replace("/0", "/1"),
    include=[
        "app.tasks.character_tasks",
        "app.tasks.video_tasks",
        "app.tasks.tts_tasks",
        "app.tasks.sfx_tasks",
        "app.tasks.assembly_tasks",
        "app.tasks.quality_tasks",
        "app.tasks.pipeline_tasks",
    ],
)

_redis_ssl = {"ssl_cert_reqs": ssl.CERT_NONE}

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_use_ssl=_redis_ssl if settings.redis_url.startswith("rediss://") else None,
    redis_backend_use_ssl=_redis_ssl if settings.redis_url.startswith("rediss://") else None,
    task_routes={
        "app.tasks.character_tasks.*": {"queue": "gpu_queue"},
        "app.tasks.video_tasks.*": {"queue": "gpu_queue"},
        "app.tasks.tts_tasks.*": {"queue": "cpu_queue"},
        "app.tasks.sfx_tasks.*": {"queue": "cpu_queue"},
        "app.tasks.assembly_tasks.*": {"queue": "cpu_queue"},
        "app.tasks.quality_tasks.*": {"queue": "cpu_queue"},
        "app.tasks.pipeline_tasks.*": {"queue": "cpu_queue"},
    },
)
