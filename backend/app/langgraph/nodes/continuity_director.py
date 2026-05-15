"""Agent Sequence Continuity & Motion Coherence Director.

Sits between cinematic_decomposer and video_editor.
Single Claude call over the full shot list — cross-shot continuity needs global context.
Falls back gracefully: if LLM fails, shots pass through unchanged.
"""
from __future__ import annotations
import logging
import re
import uuid

from ...services.llm_service import chat_json, LLMError
from ...services.sse_service import publish_event
from ...utils.prompt_templates import CONTINUITY_DIRECTOR_SYSTEM, continuity_director_user
from ..state import ProductionState

logger = logging.getLogger(__name__)


async def continuity_director_node(state: ProductionState) -> dict:
    """
    Sequence Continuity & Motion Coherence Director node.
    Runs after cinematic_decomposer, before video_editor.
    """
    project_id = state["project_id"]
    shots: list[dict] = state.get("shots") or []
    lookbook: dict = state.get("lookbook") or {}
    genre: str = state.get("genre") or "drama"
    style: str = state.get("style") or "cinematic"

    await publish_event(project_id, {
        "type": "agent_start",
        "agent": "continuity_director",
        "message": f"Continuity Director đang phân tích {len(shots)} shots để tạo Master Render List...",
    })

    if not shots:
        logger.warning("continuity_director: no shots in state — skipping")
        await publish_event(project_id, {
            "type": "agent_done",
            "agent": "continuity_director",
            "shot_count": 0,
            "message": "Không có shots để phân tích continuity.",
        })
        return {
            "shots": shots,
            "continuity_manifest": None,
            "current_stage": "continuity_director",
        }

    # ── Single LLM call: full sequence context ────────────────────────────
    user_prompt = continuity_director_user(
        shots=shots,
        lookbook=lookbook,
        genre=genre,
        style=style,
        project_id=project_id,
    )

    manifest: dict | None = None
    enriched_shots = shots

    try:
        result = await chat_json(
            CONTINUITY_DIRECTOR_SYSTEM,
            user_prompt,
            temperature=0.2,
            max_tokens=8192,
        )

        workflow_steps: list[dict] = result.get("workflow_steps") or []

        if workflow_steps:
            step_by_clip_id: dict[str, dict] = {
                step["clip_id"]: step
                for step in workflow_steps
                if step.get("clip_id")
            }

            enriched: list[dict] = []
            for shot in shots:
                shot_id = shot.get("shot_id", "")
                step = step_by_clip_id.get(shot_id)

                if step:
                    original_prompt = shot.get("prompt", "")
                    prefix_line = _extract_continuity_prefix(
                        step.get("video_prompt", ""), original_prompt
                    )
                    enriched_prompt = (
                        f"{prefix_line} {original_prompt}" if prefix_line else original_prompt
                    )
                    enriched.append({
                        **shot,
                        "prompt": enriched_prompt,
                        "continuity_notes": step.get("continuity_notes"),
                        "sfx_prompt": step.get("sfx_prompt"),
                        "ambience": (step.get("ambience") or "")[:500] or None,
                        "motion_intensity": _clamp_intensity(step.get("motion_intensity")),
                    })
                else:
                    enriched.append(shot)

            enriched_shots = enriched
            await _save_continuity_fields(project_id, enriched_shots)

            manifest = {
                "sequence_id": result.get("sequence_id", f"SEQ_001_{project_id}"),
                "total_duration": result.get("total_duration", f"{sum(s.get('duration', 8) for s in shots)}s"),
                "motion_intensity_avg": result.get("motion_intensity_avg"),
                "workflow_steps": workflow_steps,
            }

        logger.info(
            "continuity_director: %d shots enriched, motion_intensity_avg=%s",
            len(enriched_shots),
            (manifest or {}).get("motion_intensity_avg"),
        )

    except (LLMError, Exception) as e:
        logger.warning("continuity_director LLM failed (non-fatal fallback): %s", e)
        manifest = None
        enriched_shots = shots

    await publish_event(project_id, {
        "type": "agent_done",
        "agent": "continuity_director",
        "shot_count": len(enriched_shots),
        "motion_intensity_avg": (manifest or {}).get("motion_intensity_avg"),
        "message": (
            f"Master Render List sẵn sàng — {len(enriched_shots)} shots, "
            f"avg intensity {(manifest or {}).get('motion_intensity_avg', 'N/A')}"
            if manifest
            else "Continuity Director fallback — shots giữ nguyên."
        ),
    })

    return {
        "shots": enriched_shots,
        "continuity_manifest": manifest,
        "current_stage": "continuity_director",
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_continuity_prefix(video_prompt_from_llm: str, original_prompt: str) -> str:
    """
    Extract only the [CONTINUITY: ...] prefix line from Claude's video_prompt field.
    The original prompt tokens are preserved verbatim — we never use Claude's rewrite of them.
    """
    match = re.match(r"(\[CONTINUITY:[^\]]*\])", video_prompt_from_llm.strip())
    if match:
        return match.group(1)
    # Fallback: if Claude didn't use exact format, try to extract anything before original prompt starts
    if original_prompt and len(original_prompt) >= 30:
        anchor = original_prompt[:30]
        idx = video_prompt_from_llm.find(anchor)
        if idx > 0:
            prefix_part = video_prompt_from_llm[:idx].strip()
            if prefix_part and len(prefix_part) < 300:
                return prefix_part
    return ""


def _clamp_intensity(value) -> int | None:
    """Clamp motion_intensity to 0-10 integer. Returns None if value is invalid."""
    if value is None:
        return None
    try:
        return max(0, min(10, int(value)))
    except (TypeError, ValueError):
        return None


async def _save_continuity_fields(project_id: str, enriched_shots: list[dict]) -> None:
    """
    Bulk-update the 4 continuity columns on shots matched by shot_id + project_id.
    Only updates shots that have at least one non-None continuity field.
    """
    from ...database import AsyncSessionLocal
    from ...models.shot import Shot
    from sqlalchemy import select

    pid = uuid.UUID(project_id)

    continuity_map = {
        s["shot_id"]: s
        for s in enriched_shots
        if s.get("shot_id") and (
            s.get("continuity_notes") is not None
            or s.get("sfx_prompt") is not None
            or s.get("ambience") is not None
            or s.get("motion_intensity") is not None
        )
    }

    if not continuity_map:
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Shot).where(
                Shot.project_id == pid,
                Shot.shot_id.in_(list(continuity_map.keys())),
            )
        )
        db_shots = result.scalars().all()

        for db_shot in db_shots:
            data = continuity_map.get(db_shot.shot_id)
            if data:
                db_shot.prompt = data.get("prompt", db_shot.prompt)
                db_shot.continuity_notes = data.get("continuity_notes")
                db_shot.sfx_prompt = data.get("sfx_prompt")
                db_shot.ambience = (data.get("ambience") or "")[:500] or None
                db_shot.motion_intensity = data.get("motion_intensity")

        await db.commit()

    logger.info(
        "continuity_director: %d/%d shots updated in DB",
        len(db_shots), len(continuity_map),
    )
