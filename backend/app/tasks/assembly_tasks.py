"""Celery task — FFmpeg assembly: concat clips + mix voiceover + music."""
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
    name="assembly_tasks.assemble_video",
    queue="cpu_queue",
    acks_late=True,
    max_retries=1,
)
def assemble_video(self, results: list, project_id: str, voiceover_key: str | None = None, music_key: str | None = None):
    """
    Called as the Celery chord callback after all video clips + voiceover are ready.
    `results` = list of r2_keys from upstream tasks (video clips).
    """
    return _run(_assemble_async(self, project_id, results, voiceover_key, music_key))


async def _assemble_async(task, project_id, results, voiceover_key, music_key, subtitle_srt: str = ""):
    from ..database import AsyncSessionLocal
    from ..models.project import Project, ProjectStatus
    from ..models.generation_task import GenerationTask, TaskType, TaskStatus
    from ..models.scene import Scene
    from ..services.r2_service import upload_bytes, download_bytes
    from ..services.ffmpeg_service import assemble_video as ffmpeg_assemble
    from ..services.sse_service import publish_event

    pid = uuid.UUID(project_id)

    await publish_event(project_id, {
        "type": "task_start",
        "task_type": "assembly",
        "message": "Đang dựng video (FFmpeg)...",
    })

    async with AsyncSessionLocal() as db:
        gt = GenerationTask(
            project_id=pid,
            task_type=TaskType.assembly,
            celery_task_id=task.request.id,
            status=TaskStatus.running, attempts=1,
        )
        db.add(gt)
        await db.commit()
        await db.refresh(gt)
        gt_id = gt.id

    try:
        # Collect clip R2 keys from DB (ordered by scene_number)
        from sqlalchemy import select
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Scene)
                .where(Scene.project_id == pid, Scene.clip_r2_key.isnot(None))
                .order_by(Scene.scene_number)
            )
            scenes = result.scalars().all()

        # Download clip bytes
        clip_bytes_list = []
        for scene in scenes:
            try:
                clip_bytes_list.append(await download_bytes(scene.clip_r2_key))
            except Exception as e:
                logger.warning("Could not download clip %s: %s", scene.clip_r2_key, e)

        if not clip_bytes_list:
            raise RuntimeError("No video clips available for assembly")

        # Download voiceover
        voiceover_bytes = None
        if voiceover_key:
            try:
                voiceover_bytes = await download_bytes(voiceover_key)
            except Exception as e:
                logger.warning("Could not download voiceover: %s", e)

        # Download music
        music_bytes = None
        if music_key:
            try:
                music_bytes = await download_bytes(music_key)
            except Exception as e:
                logger.warning("Could not download music: %s", e)

        # FFmpeg assembly
        final_bytes = await ffmpeg_assemble(clip_bytes_list, voiceover_bytes, music_bytes)

        # Burn subtitles into assembled video (non-fatal)
        if subtitle_srt:
            try:
                from ..services.subtitle_service import burn_subtitles_into_video
                final_bytes = await burn_subtitles_into_video(final_bytes, subtitle_srt, project_id)
            except Exception as e:
                logger.warning("Subtitle burn failed (non-fatal): %s", e)

        # Upload final video to R2
        final_key = f"projects/{project_id}/final.mp4"
        await upload_bytes(final_key, final_bytes, content_type="video/mp4")

        # Update project
        async with AsyncSessionLocal() as db:
            proj = await db.get(Project, pid)
            if proj:
                proj.final_video_r2_key = final_key
                proj.status = ProjectStatus.quality_review
            gt = await db.get(GenerationTask, gt_id)
            if gt:
                gt.status = TaskStatus.success
                gt.result_r2_key = final_key
                gt.progress_pct = 100
            await db.commit()

        await publish_event(project_id, {
            "type": "task_done",
            "task_type": "assembly",
            "r2_key": final_key,
            "message": "Video đã dựng xong! Đang chuyển sang chấm điểm chất lượng.",
        })
        return final_key

    except Exception as e:
        logger.error("Assembly failed for project %s: %s", project_id, e)
        async with AsyncSessionLocal() as db:
            gt = await db.get(GenerationTask, gt_id)
            if gt:
                gt.status = TaskStatus.failed
                gt.error_message = str(e)
            await db.commit()
        await publish_event(project_id, {
            "type": "task_error",
            "task_type": "assembly",
            "error": str(e),
        })
        raise
