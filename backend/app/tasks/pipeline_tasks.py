"""Celery chord pipeline — orchestrate video production tasks.

Flow:
  launch_production_pipeline(project_id)
    └── chord(
          group(video_clip × N scenes, voiceover),
          assemble_video callback
        )
"""
import asyncio
import logging
import uuid
from celery import group, chord
from .celery_app import celery_app


class _MockTask:
    """Fake Celery task context — used when running tasks inline without a worker."""
    def __init__(self):
        self.request = type("_req", (), {"id": str(uuid.uuid4())})()


async def run_production_pipeline_inline(project_id: str, music_key: str | None = None) -> None:
    """
    Run the full production pipeline inline (no Celery worker needed).
    Called from video_generator_node which runs inside a FastAPI BackgroundTask.
    Sequence: video clips (sequential) → voiceover → assemble.
    """
    from ..database import AsyncSessionLocal
    from ..models.scene import Scene
    from ..models.script import Script
    from ..models.project import Project, ProjectStatus
    from ..services.sse_service import publish_event
    from .video_tasks import _generate_clip_async
    from .tts_tasks import _tts_async
    from .assembly_tasks import _assemble_async
    from sqlalchemy import select

    pid = uuid.UUID(project_id)

    await publish_event(project_id, {"type": "pipeline_start", "message": "Đang khởi động pipeline tạo video..."})

    async with AsyncSessionLocal() as db:
        scene_result = await db.execute(select(Scene).where(Scene.project_id == pid).order_by(Scene.scene_number))
        scenes = scene_result.scalars().all()

        script_result = await db.execute(select(Script).where(Script.project_id == pid).order_by(Script.version.desc()))
        script = script_result.scalars().first()
        narration_text = (script.content_raw or "") if script else ""

        proj = await db.get(Project, pid)
        language = proj.preferred_language if proj else "vi"
        aspect_ratio = "9:16" if proj and str(proj.production_type) == "short_video" else "16:9"
        if proj:
            proj.status = ProjectStatus.generating
        await db.commit()

    if not scenes:
        await publish_event(project_id, {"type": "pipeline_error", "error": "Không có cảnh nào để tạo video."})
        return

    await publish_event(project_id, {
        "type": "pipeline_queued",
        "scene_count": len(scenes),
        "message": f"Đang tạo {len(scenes)} clip + giọng đọc...",
    })

    # Generate video clips sequentially
    for scene in scenes:
        try:
            await _generate_clip_async(
                _MockTask(), project_id, str(scene.id),
                scene.video_prompt or f"Scene {scene.scene_number}: {scene.description or scene.title or ''}",
                scene.duration_seconds or 5, aspect_ratio,
            )
        except Exception as e:
            logger.error("Clip failed scene %s: %s", scene.id, e)

    # Generate voiceover
    voiceover_key: str | None = None
    try:
        voiceover_key = await _tts_async(_MockTask(), project_id, narration_text, language)
    except Exception as e:
        logger.error("Voiceover failed: %s", e)

    # Assemble final video
    try:
        await _assemble_async(_MockTask(), project_id, [], voiceover_key, music_key)
    except Exception as e:
        logger.error("Assembly failed: %s", e)
        await publish_event(project_id, {"type": "pipeline_error", "error": str(e)})

logger = logging.getLogger(__name__)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    name="pipeline_tasks.launch_production_pipeline",
    queue="cpu_queue",
)
def launch_production_pipeline(self, project_id: str, music_key: str | None = None):
    """
    Entry point: read scenes from DB, build Celery chord, launch.
    Called by LangGraph video_generator_node or directly via POST /generation/start.
    """
    return _run(_launch_async(self, project_id, music_key))


async def _launch_async(task, project_id: str, music_key: str | None):
    from ..database import AsyncSessionLocal
    from ..models.scene import Scene
    from ..models.script import Script
    from ..models.project import Project, ProjectStatus
    from ..services.sse_service import publish_event
    from .video_tasks import generate_video_clip
    from .tts_tasks import generate_voiceover
    from .assembly_tasks import assemble_video

    pid = uuid.UUID(project_id)

    await publish_event(project_id, {
        "type": "pipeline_start",
        "message": "Đang khởi động pipeline tạo video...",
    })

    # Collect scenes + script narration
    from sqlalchemy import select
    async with AsyncSessionLocal() as db:
        scene_result = await db.execute(
            select(Scene).where(Scene.project_id == pid).order_by(Scene.scene_number)
        )
        scenes = scene_result.scalars().all()

        script_result = await db.execute(
            select(Script).where(Script.project_id == pid).order_by(Script.version.desc())
        )
        script = script_result.scalars().first()
        narration_text = script.content_raw or "" if script else ""

        proj = await db.get(Project, pid)
        language = proj.preferred_language if proj else "vi"
        aspect_ratio = "9:16" if proj and str(proj.production_type) == "short_video" else "16:9"

        # Update status
        if proj:
            proj.status = ProjectStatus.generating
        await db.commit()

    if not scenes:
        logger.error("No scenes found for project %s", project_id)
        await publish_event(project_id, {
            "type": "pipeline_error",
            "error": "Không có cảnh nào để tạo video. Vui lòng phân cảnh trước.",
        })
        return

    # Build task group: one video clip per scene + one voiceover
    video_tasks = [
        generate_video_clip.s(
            project_id,
            str(scene.id),
            scene.video_prompt or f"Scene {scene.scene_number}: {scene.description or scene.title or ''}",
            scene.duration_seconds or 5,
            aspect_ratio,
        )
        for scene in scenes
    ]

    tts_task = generate_voiceover.s(project_id, narration_text, language)

    all_tasks = video_tasks + [tts_task]

    # Chord: run all tasks, then assemble
    production_chord = chord(
        group(*all_tasks),
        assemble_video.s(project_id=project_id, music_key=music_key),
    )
    production_chord.apply_async()

    logger.info("Production pipeline launched: %d clips + voiceover + assembly", len(scenes))

    await publish_event(project_id, {
        "type": "pipeline_queued",
        "scene_count": len(scenes),
        "message": f"Đã xếp hàng {len(scenes)} clip + giọng đọc. Celery đang xử lý...",
    })
    return {"queued": True, "scene_count": len(scenes)}
