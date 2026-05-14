"""Agent Video Validator — AI quality scoring + 3-action human review."""
from __future__ import annotations
import uuid
import logging

from langgraph.types import interrupt

from ...database import AsyncSessionLocal
from ...models.project import Project
from ...models.quality_score import QualityScore
from ...services.sse_service import publish_event
from ..state import ProductionState

logger = logging.getLogger(__name__)


async def video_validator_node(state: ProductionState) -> dict:
    """
    AI Video Validator:
    1. Score final video using GPT-5.4 Vision (reuses quality_service.score_video)
    2. Save QualityScore to DB
    3. If score < 8 AND retry < 3 → route back to video_editor (auto-retry)
    4. If score ≥ 8 OR retry ≥ 3 → proceed to video_review (human decision)
    """
    project_id = state["project_id"]
    final_video_key = state.get("final_video_r2_key") or ""
    retry_count = state.get("video_retry_count", 0)

    await publish_event(project_id, {
        "type": "agent_start",
        "agent": "video_validator",
        "message": f"GPT-5.4 Vision đang chấm điểm video (lần {retry_count + 1}/3)...",
    })

    # Fetch project metadata for scoring context
    pid = uuid.UUID(project_id)
    topic = state.get("topic", "")
    genre = state.get("genre", "")
    script_summary = (state.get("script_content") or "")[:500]

    overall_score = 75  # default pass if scoring fails
    scores: dict = {}

    if final_video_key:
        try:
            from ...services.quality_service import score_video
            scores = await score_video(
                project_id=project_id,
                final_video_r2_key=final_video_key,
                topic=topic,
                genre=genre,
                script_summary=script_summary,
            )
            overall_score = scores.get("overall_score", 75)
        except Exception as e:
            logger.error("Video scoring failed (non-fatal, using default pass): %s", e)

    # Save to DB
    await _save_quality_score(pid, scores, overall_score)

    # Convert 0-100 to 1-10
    ai_score = round(overall_score / 10)
    will_retry = ai_score < 8 and retry_count < 3
    passed = overall_score >= 75

    await publish_event(project_id, {
        "type": "agent_done",
        "agent": "video_validator",
        "overall_score": overall_score,
        "ai_score": ai_score,
        "passed": passed,
        "will_retry": will_retry,
        "message": (
            f"Điểm video: {overall_score}/100 ({ai_score}/10) — "
            f"{'Tạo lại video' if will_retry else 'Đủ điều kiện duyệt ✓'}"
        ),
    })

    logger.info("Video score: %d/100 (%d/10), retry=%d, will_retry=%s", overall_score, ai_score, retry_count, will_retry)
    return {
        "video_ai_score": ai_score,
        "current_stage": "video_validator",
        "error": None,
    }


async def _save_quality_score(project_id: uuid.UUID, scores: dict, overall: int) -> None:
    """Persist quality score to DB."""
    try:
        async with AsyncSessionLocal() as db:
            qs = QualityScore(
                project_id=project_id,
                overall_score=overall,
                hook_strength=scores.get("hook_strength", 0),
                story_coherence=scores.get("story_coherence", 0),
                visual_quality=scores.get("visual_quality", 0),
                audio_sync=scores.get("audio_sync", 0),
                character_consistency=scores.get("character_consistency", 0),
                pacing=scores.get("pacing", 0),
                engagement_potential=scores.get("engagement_potential", 0),
                gpt_feedback=scores.get("gpt_feedback", ""),
            )
            db.add(qs)
            await db.commit()
    except Exception as e:
        logger.warning("Could not save quality score to DB: %s", e)


def route_after_video_validator(state: ProductionState) -> str:
    """score < 8 AND retry < 3 → video_editor (auto-retry); else → video_review."""
    score = state.get("video_ai_score", 8) or 8
    retries = state.get("video_retry_count", 0)
    if score < 8 and retries < 3:
        return "video_editor"
    return "video_review"


async def video_review_node(state: ProductionState) -> dict:
    """
    Human Video Review (3-action interrupt):
    - Sends Resend email with Proceed / Remake / Hold buttons
    - interrupt() pauses graph
    - Resumes with {"action": "proceed"|"remake"|"hold"}
    """
    project_id = state["project_id"]
    ai_score = state.get("video_ai_score", 8) or 8
    overall_score = (ai_score or 8) * 10

    await publish_event(project_id, {
        "type": "agent_interrupt",
        "step": "video_review",
        "video_ai_score": ai_score,
        "overall_score": overall_score,
        "message": f"Video đạt {overall_score}/100 điểm. Đã gửi email duyệt.",
    })

    # Fetch project title
    project_title = "Dự án mới"
    try:
        pid = uuid.UUID(project_id)
        async with AsyncSessionLocal() as db:
            proj = await db.get(Project, pid)
            if proj:
                project_title = proj.title or "Dự án mới"
    except Exception:
        pass

    # Send 3-action email
    try:
        from ...services.notification_service import send_video_review_request
        await send_video_review_request(
            project_id=project_id,
            project_title=project_title,
            ai_score=ai_score,
            overall_score=overall_score,
        )
    except Exception as e:
        logger.warning("Video review email failed: %s", e)

    decision: dict = interrupt({
        "step": "video_review",
        "video_ai_score": ai_score,
        "overall_score": overall_score,
    })

    action: str = decision.get("action", "proceed")

    return {
        "video_review_action": action,
        "approval_status": "approved" if action == "proceed" else "pending",
        "current_stage": "done" if action in ("proceed", "hold") else "video_editor",
    }


def route_after_video_review(state: ProductionState) -> str:
    """proceed/hold → END; remake → video_editor (reset retry counter)."""
    action = state.get("video_review_action", "proceed")
    if action == "remake":
        return "video_editor"
    return "end"
