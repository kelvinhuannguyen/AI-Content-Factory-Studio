"""Agent Screenwriter — viết kịch bản Hollywood. Không có interrupt — auto-advance."""
from __future__ import annotations
import json
import uuid
import logging

from ...config import get_settings
from ...database import AsyncSessionLocal
from ...models.script import Script
from ...models.project import Project, ProjectStatus
from ...services.llm_service import chat_json, LLMError
from ...services.sse_service import publish_event
from ...utils.prompt_templates import SCRIPT_SYSTEM, script_user
from ..state import ProductionState

logger = logging.getLogger(__name__)
settings = get_settings()


async def _fetch_project_title(project_id: str) -> str:
    """Fetch project title from DB for email notifications."""
    try:
        pid = uuid.UUID(project_id)
        async with AsyncSessionLocal() as db:
            proj = await db.get(Project, pid)
            return proj.title if proj and proj.title else "Dự án mới"
    except Exception:
        return "Dự án mới"


def _script_to_html(result: dict) -> str:
    """Convert GPT JSON → basic HTML for Tiptap editor."""
    parts = []
    if result.get("title"):
        parts.append(f"<h2>{result['title']}</h2>")
    if result.get("hook"):
        parts.append(f"<p><strong>[HOOK]</strong> {result['hook']}</p>")
    for scene in result.get("scenes", []):
        parts.append(
            f"<h3>Cảnh {scene.get('scene_number', '?')}: {scene.get('title', '')} "
            f"({scene.get('duration_seconds', 0)}s)</h3>"
        )
        if scene.get("narration"):
            parts.append(f"<p><em>{scene['narration']}</em></p>")
        if scene.get("shot_description"):
            parts.append(f"<p><strong>[Cảnh quay]</strong> {scene['shot_description']}</p>")
    return "".join(parts) or f"<p>{result.get('full_script_text', '')}</p>"


async def screenwriter_node(state: ProductionState) -> dict:
    """
    Agent Screenwriter:
    1. Gọi KymaAPI (gemini-2.5-flash) → kịch bản Hollywood JSON
    2. Lưu Script vào DB (tăng version nếu regenerate)
    3. Update Project.status → script_ready
    4. Publish SSE event để frontend nhận biết
    """
    project_id = state["project_id"]
    topic = state.get("topic") or ""
    notes = state.get("rejection_notes") or ""
    # Increment retry counter when screenwriter is called again after AI scoring
    prior_score = state.get("script_ai_score")
    retry_count = state.get("script_retry_count", 0)
    if prior_score is not None and prior_score < 8:
        retry_count = retry_count + 1

    await publish_event(project_id, {
        "type": "agent_start",
        "agent": "screenwriter",
        "message": f"Đang viết kịch bản{'(lần ' + str(retry_count + 1) + ')' if retry_count > 0 else ''}...",
    })

    # Build prompt (append rejection notes if regenerating)
    additional_notes = notes if notes else ""
    user_prompt = script_user(
        topic=topic,
        genre=state.get("genre", ""),
        style=state.get("style", ""),
        duration_seconds=state.get("duration_seconds", 60),
        production_type=state.get("production_type", "short_video"),
        language=state.get("language", "vi"),
        additional_notes=additional_notes,
    )

    # Primary: gemini-2.5-flash (fast, 10-30s)
    # Fallback: deepseek-v3 (slower 2-4min but handles mature drama topics gemini filters)
    result: dict | None = None
    for model in [settings.kymaapi_llm_model, settings.kymaapi_llm_model_long]:
        try:
            result = await chat_json(SCRIPT_SYSTEM, user_prompt, temperature=0.8, max_tokens=6000, model=model)
            if isinstance(result, dict) and result.get("scenes"):
                logger.info("Screenwriter success with model=%s", model)
                break
            logger.warning("Screenwriter model=%s returned no scenes — trying next", model)
            result = None
        except LLMError as e:
            logger.warning("Screenwriter model=%s failed: %s — trying next", model, e)

    if not result:
        err = "All screenwriter models failed to produce a valid script"
        logger.error(err)
        await publish_event(project_id, {"type": "agent_error", "agent": "screenwriter", "error": err})
        return {"error": err, "current_stage": "screenwriter"}

    full_text: str = result.get("full_script_text", "")
    content_html = _script_to_html(result)
    word_count = len(full_text.split())

    # Persist to DB
    script_id: str | None = None
    async with AsyncSessionLocal() as db:
        try:
            from sqlalchemy import select
            pid = uuid.UUID(project_id)
            existing = await db.execute(
                select(Script).where(Script.project_id == pid).order_by(Script.version.desc())
            )
            latest = existing.scalars().first()
            version = (latest.version + 1) if latest else 1

            script = Script(
                project_id=pid,
                version=version,
                # Store full JSON so _generate_scene_prompts can use scenes directly
                # without an extra LLM parsing call
                content_raw=json.dumps(result, ensure_ascii=False),
                content_html=content_html,
                word_count=word_count,
                estimated_duration_seconds=result.get("total_estimated_seconds", state.get("duration_seconds", 60)),
            )
            db.add(script)

            proj = await db.get(Project, pid)
            if proj:
                proj.status = ProjectStatus.script_ready
                proj.topic = topic

            await db.commit()
            await db.refresh(script)
            script_id = str(script.id)
        except Exception as e:
            logger.error("Screenwriter DB error: %s", e)
            await db.rollback()

    await publish_event(project_id, {
        "type": "agent_done",
        "agent": "screenwriter",
        "script_id": script_id,
        "word_count": word_count,
        "message": f"Kịch bản đã viết xong ({word_count} từ). Vui lòng duyệt.",
    })

    # Build plain-text narration for IP Architect (character extractor)
    plain_narration = full_text or "\n".join(
        f"{s.get('narration', '')} {s.get('shot_description', '')}"
        for s in result.get("scenes", [])
    )

    return {
        "script_id": script_id,
        "script_content": plain_narration,
        "script_html": content_html,
        "script_approved": False,
        "script_ai_score": None,   # reset so scorer re-evaluates fresh script
        "script_retry_count": retry_count,
        "approval_status": "pending",
        "rejection_notes": None,
        "current_stage": "script_scorer",
        "error": None,
    }


async def script_review_node(state: ProductionState) -> dict:
    """Auto-approve: no interrupt. Script passes directly to character_designer."""
    return {
        "script_approved": True,
        "approval_status": "approved",
        "current_stage": "character_designer",
        "paused_at": None,
    }


def route_after_script_review(state: ProductionState) -> str:
    return "character_designer"
