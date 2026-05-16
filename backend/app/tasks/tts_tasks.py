"""Celery task — generate full voiceover for the project."""
import asyncio
import logging
import uuid
from .celery_app import celery_app

logger = logging.getLogger(__name__)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    name="tts_tasks.generate_voiceover",
    queue="cpu_queue",
    acks_late=True,
    max_retries=2,
    default_retry_delay=10,
)
def generate_voiceover(self, project_id: str, narration_text: str, language: str = "vi", narrator_gender: str = "woman"):
    return _run(_tts_async(self, project_id, narration_text, language, narrator_gender))


async def _tts_async(task, project_id, narration_text, language, narrator_gender="woman"):
    from ..database import AsyncSessionLocal
    from ..models.generation_task import GenerationTask, TaskType, TaskStatus
    from ..services.elevenlabs_service import generate_voiceover as tts_gen, TTSError
    from ..services.r2_service import upload_bytes
    from ..services.sse_service import publish_event

    pid = uuid.UUID(project_id)
    r2_key = f"projects/{project_id}/voiceover.mp3"

    await publish_event(project_id, {
        "type": "task_start",
        "task_type": "voiceover",
        "message": "Đang tạo giọng đọc...",
    })

    async with AsyncSessionLocal() as db:
        gt = GenerationTask(
            project_id=pid,
            task_type=TaskType.voiceover,
            celery_task_id=task.request.id,
            status=TaskStatus.running, attempts=1,
        )
        db.add(gt)
        await db.commit()
        await db.refresh(gt)
        gt_id = gt.id

    try:
        audio_bytes = await tts_gen(narration_text, language=language, narrator_gender=narrator_gender)
        await upload_bytes(r2_key, audio_bytes, content_type="audio/mpeg")

        async with AsyncSessionLocal() as db:
            gt = await db.get(GenerationTask, gt_id)
            if gt:
                gt.status = TaskStatus.success
                gt.result_r2_key = r2_key
                gt.progress_pct = 100
            await db.commit()

        await publish_event(project_id, {
            "type": "task_done",
            "task_type": "voiceover",
            "r2_key": r2_key,
        })
        return r2_key

    except (TTSError, Exception) as e:
        logger.error("TTS failed for project %s: %s", project_id, e)
        async with AsyncSessionLocal() as db:
            gt = await db.get(GenerationTask, gt_id)
            if gt:
                gt.status = TaskStatus.failed
                gt.error_message = str(e)
            await db.commit()
        await publish_event(project_id, {
            "type": "task_error",
            "task_type": "voiceover",
            "error": str(e),
        })
        raise
