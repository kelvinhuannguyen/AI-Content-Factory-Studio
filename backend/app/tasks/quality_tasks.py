"""Celery task — score video quality with GPT-5.4 Vision (fallback GPT-5.5)."""
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
    name="quality_tasks.score_quality",
    queue="cpu_queue",
    acks_late=True,
    max_retries=2,
    default_retry_delay=15,
)
def score_quality(self, project_id: str):
    """Score the final assembled video using GPT-5.4 Vision (fallback GPT-5.5)."""
    return _run(_score_async(self, project_id))


async def _score_async(task, project_id: str):
    from ..database import AsyncSessionLocal
    from ..models.project import Project, ProjectStatus
    from ..models.script import Script
    from ..models.quality_score import QualityScore
    from ..services.quality_service import score_video, QualityError
    from ..services.sse_service import publish_event
    from sqlalchemy import select
    from datetime import datetime, timezone

    pid = uuid.UUID(project_id)

    await publish_event(project_id, {
        "type": "task_start",
        "task_type": "quality_score",
        "message": "Đang chấm điểm chất lượng video (GPT-5.4 Vision)...",
    })

    # Gather project data
    async with AsyncSessionLocal() as db:
        proj = await db.get(Project, pid)
        if not proj or not proj.final_video_r2_key:
            await publish_event(project_id, {
                "type": "task_error",
                "task_type": "quality_score",
                "error": "Chưa có video final để chấm điểm",
            })
            return

        script_res = await db.execute(
            select(Script).where(Script.project_id == pid).order_by(Script.version.desc())
        )
        script = script_res.scalars().first()
        script_summary = (script.content_raw or "")[:600] if script else ""

        topic = proj.topic or ""
        genre = proj.genre or ""
        final_key = proj.final_video_r2_key

    # Score
    try:
        scores = await score_video(
            project_id=project_id,
            final_video_r2_key=final_key,
            topic=topic,
            genre=genre,
            script_summary=script_summary,
        )
    except QualityError as e:
        logger.error("Quality scoring failed for %s: %s", project_id, e)
        await publish_event(project_id, {
            "type": "task_error",
            "task_type": "quality_score",
            "error": str(e),
        })
        raise

    # Persist QualityScore to DB
    async with AsyncSessionLocal() as db:
        qs = QualityScore(
            project_id=pid,
            overall_score=scores["overall_score"],
            hook_strength=scores["hook_strength"],
            story_coherence=scores["story_coherence"],
            visual_quality=scores["visual_quality"],
            audio_sync=scores["audio_sync"],
            character_consistency=scores["character_consistency"],
            pacing=scores["pacing"],
            engagement_potential=scores["engagement_potential"],
            gpt_feedback=scores["gpt_feedback"],
            scored_at=datetime.now(timezone.utc),
        )
        db.add(qs)

        proj = await db.get(Project, pid)
        if proj:
            proj.status = ProjectStatus.quality_review
        await db.commit()
        await db.refresh(qs)
        qs_id = str(qs.id)

    await publish_event(project_id, {
        "type": "quality_scored",
        "task_type": "quality_score",
        "score_id": qs_id,
        "overall_score": scores["overall_score"],
        "passed": scores["overall_score"] >= 75,
        "scores": scores,
        "message": f"Chấm điểm xong: {scores['overall_score']}/100 — {'Đạt' if scores['overall_score'] >= 75 else 'Chưa đạt (< 75)'}",
    })

    logger.info("Quality score for %s: %d/100", project_id, scores["overall_score"])
    return scores
