"""Quality API — trigger scoring, get scores, human review decision."""
import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ...database import get_db
from ...models.project import Project, ProjectStatus
from ...models.quality_score import QualityScore
from ...tasks.quality_tasks import score_quality

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/score", status_code=202)
async def trigger_quality_score(body: dict, db: AsyncSession = Depends(get_db)):
    """
    Enqueue GPT-5.4 Vision quality scoring for a project.
    Body: { project_id }
    Scoring runs async in Celery — follow progress via SSE stream.
    """
    project_id = body.get("project_id")
    if not project_id:
        raise HTTPException(422, "project_id required")

    try:
        pid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(422, "Invalid project_id")

    proj = await db.get(Project, pid)
    if not proj:
        raise HTTPException(404, "Project not found")

    if not proj.final_video_r2_key:
        raise HTTPException(422, "Chưa có video final. Chạy pipeline tạo video trước.")

    task = score_quality.apply_async(
        kwargs={"project_id": project_id},
        queue="cpu_queue",
    )

    return {
        "status": "queued",
        "celery_task_id": task.id,
        "model_primary": "gpt-5.4",
        "model_fallback": "gpt-5.5",
        "message": "Đang chấm điểm bằng GPT-5.4 Vision. Theo dõi qua SSE stream.",
    }


@router.get("/{project_id}")
async def get_quality_score(project_id: str, db: AsyncSession = Depends(get_db)):
    """Get the latest quality score for a project, including final video URL."""
    try:
        pid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(422, "Invalid project_id")

    result = await db.execute(
        select(QualityScore)
        .where(QualityScore.project_id == pid)
        .order_by(QualityScore.scored_at.desc())
    )
    qs = result.scalars().first()
    if not qs:
        raise HTTPException(404, "Chưa có điểm chất lượng. Trigger /score trước.")

    # Resolve final video URL for the player
    video_url: str | None = None
    proj = await db.get(Project, pid)
    if proj and proj.final_video_r2_key:
        from ...services.r2_service import public_url, generate_presigned_url
        video_url = public_url(proj.final_video_r2_key)
        if not video_url:
            try:
                video_url = await generate_presigned_url(proj.final_video_r2_key)
            except Exception:
                video_url = None

    return _score_to_dict(qs, video_url=video_url)


@router.post("/{project_id}/review")
async def submit_human_review(
    project_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """
    Human approves or rejects video quality.
    Body: { approved: bool, rejection_notes?: str }
    Advances project status to human_review → seo_ready (approved) or generating (rejected).
    """
    try:
        pid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(422, "Invalid project_id")

    proj = await db.get(Project, pid)
    if not proj:
        raise HTTPException(404, "Project not found")

    approved: bool = bool(body.get("approved", False))
    notes: str = body.get("rejection_notes", "")

    # Update latest quality score
    result = await db.execute(
        select(QualityScore)
        .where(QualityScore.project_id == pid)
        .order_by(QualityScore.scored_at.desc())
    )
    qs = result.scalars().first()
    if qs:
        qs.human_approved = approved
        qs.rejection_notes = notes if not approved else None

    # Advance project status
    if approved:
        proj.status = ProjectStatus.seo_ready
    else:
        # Rejected — reset to generating so user can re-run pipeline
        proj.status = ProjectStatus.generating

    await db.commit()

    # Resume LangGraph if pipeline is running
    try:
        from ...langgraph.graph import get_graph
        from ...langgraph.checkpointer import get_thread_config
        from langgraph.types import Command

        graph = await get_graph()
        config = get_thread_config(project_id)
        state = await graph.aget_state(config)
        if state and state.next:
            await graph.ainvoke(
                Command(resume={"approved": approved, "notes": notes}),
                config=config,
            )
    except Exception as e:
        logger.debug("LangGraph resume skipped (quality review): %s", e)

    return {
        "approved": approved,
        "project_status": proj.status,
        "message": "Đã duyệt — tiếp tục tạo SEO package." if approved else "Đã từ chối — có thể tạo lại video.",
    }


def _score_to_dict(qs: QualityScore, video_url: str | None = None) -> dict:
    return {
        "id": str(qs.id),
        "video_url": video_url,
        "project_id": str(qs.project_id),
        "overall_score": qs.overall_score,
        "passed": qs.overall_score >= 75,
        "dimensions": {
            "hook_strength":          {"score": qs.hook_strength,          "max": 20},
            "story_coherence":        {"score": qs.story_coherence,        "max": 20},
            "visual_quality":         {"score": qs.visual_quality,         "max": 20},
            "audio_sync":             {"score": qs.audio_sync,             "max": 15},
            "character_consistency":  {"score": qs.character_consistency,  "max": 10},
            "pacing":                 {"score": qs.pacing,                 "max": 10},
            "engagement_potential":   {"score": qs.engagement_potential,   "max":  5},
        },
        "gpt_feedback": qs.gpt_feedback,
        "human_approved": qs.human_approved,
        "rejection_notes": qs.rejection_notes,
        "scored_at": qs.scored_at.isoformat() if qs.scored_at else None,
        "model_used": "gpt-5.4 / gpt-5.5 fallback",
    }
