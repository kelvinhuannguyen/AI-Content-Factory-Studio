"""Celery task — generate one video clip for a scene."""
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
    name="video_tasks.generate_video_clip",
    queue="gpu_queue",
    acks_late=True,
    max_retries=2,
    default_retry_delay=15,
)
def generate_video_clip(self, project_id: str, scene_id: str, video_prompt: str, duration_seconds: int, aspect_ratio: str = "9:16"):
    return _run(_generate_clip_async(self, project_id, scene_id, video_prompt, duration_seconds, aspect_ratio))


async def _generate_clip_async(task, project_id, scene_id, video_prompt, duration_seconds, aspect_ratio):
    from ..database import AsyncSessionLocal
    from ..models.scene import Scene, SceneStatus
    from ..models.generation_task import GenerationTask, TaskType, TaskStatus
    from ..services.kyma_video_service import generate_video_clip as kyma_gen, VideoGenError
    from ..services.r2_service import upload_bytes
    from ..services.sse_service import publish_event

    sid = uuid.UUID(scene_id)
    pid = uuid.UUID(project_id)

    await publish_event(project_id, {
        "type": "task_start",
        "task_type": "video_clip",
        "scene_id": scene_id,
        "message": f"Đang tạo video clip cảnh...",
    })

    # Create GenerationTask record
    async with AsyncSessionLocal() as db:
        gt = GenerationTask(
            project_id=pid, scene_id=sid,
            task_type=TaskType.video_clip,
            celery_task_id=task.request.id,
            status=TaskStatus.running, attempts=1,
        )
        db.add(gt)
        await db.commit()
        await db.refresh(gt)
        gt_id = gt.id

    r2_key = f"projects/{project_id}/scenes/{scene_id}/clip.mp4"
    try:
        video_bytes = await kyma_gen(video_prompt, duration_seconds=duration_seconds, aspect_ratio=aspect_ratio)
        await upload_bytes(r2_key, video_bytes, content_type="video/mp4")

        async with AsyncSessionLocal() as db:
            # Try Shot first (cinematic_decomposer mode passes Shot.id as scene_id)
            from ..models.shot import Shot as ShotModel
            shot_row = await db.get(ShotModel, sid)
            if shot_row:
                shot_row.clip_r2_key = r2_key
            else:
                scene_row = await db.get(Scene, sid)
                if scene_row:
                    scene_row.clip_r2_key = r2_key
                    scene_row.status = SceneStatus.ready
            gt = await db.get(GenerationTask, gt_id)
            if gt:
                gt.status = TaskStatus.success
                gt.result_r2_key = r2_key
                gt.progress_pct = 100
            await db.commit()

        await publish_event(project_id, {
            "type": "task_done",
            "task_type": "video_clip",
            "scene_id": scene_id,
            "r2_key": r2_key,
        })
        return r2_key

    except (VideoGenError, Exception) as e:
        logger.error("Video clip failed scene %s: %s", scene_id, e)
        async with AsyncSessionLocal() as db:
            from ..models.scene import SceneStatus
            scene = await db.get(Scene, sid)
            if scene:
                scene.status = SceneStatus.failed
            gt = await db.get(GenerationTask, gt_id)
            if gt:
                gt.status = TaskStatus.failed
                gt.error_message = str(e)
            await db.commit()
        await publish_event(project_id, {
            "type": "task_error",
            "task_type": "video_clip",
            "scene_id": scene_id,
            "error": str(e),
        })
        raise


# Celery re-imports required by celery_app.py include list
from ..models.generation_task import GenerationTask, TaskType, TaskStatus  # noqa: E402
