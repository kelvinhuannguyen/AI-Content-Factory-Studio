"""Agent Character Designer — IP Character Production Pipeline.

Flow:
  character_designer_node:
    Stage 1-3: IP Architect LLM → extract N characters with VIS + Ref IDs
    Stage 4:   Pure Python → build image prompts
    Stage 5:   Generate 1 hero portrait per character (concurrent)
  character_review_node:
    Interrupt → user reviews all N characters, approves all or regenerates specific ones
"""
from __future__ import annotations
import asyncio
import logging
import uuid

from langgraph.types import interrupt

from ...database import AsyncSessionLocal
from ...models.character import Character
from ...models.project import Project, ProjectStatus
from ...services.sse_service import publish_event
from ...services.notification_service import send_approval_request
from ..state import ProductionState

logger = logging.getLogger(__name__)


async def character_designer_node(state: ProductionState) -> dict:
    """
    IP Character Production Pipeline:
    1. IP Architect (LLM): parse script → extract N characters with VIS, DNA, Ref IDs
    2. Generate 1 hero portrait per character (concurrent) using VIS-anchored prompts
    3. Return all characters to character_review_node
    """
    project_id = state["project_id"]
    script_content = state.get("script_content") or ""

    await publish_event(project_id, {
        "type": "agent_start",
        "agent": "character_designer",
        "message": "Đang phân tích kịch bản để thiết kế nhân vật...",
    })

    # Stage 1-4: IP Pipeline
    from .character_ip_pipeline import _run_ip_pipeline, _build_fallback_profile

    if script_content:
        try:
            ip_result = await _run_ip_pipeline(state, script_content)
        except Exception as e:
            logger.error("IP pipeline failed, using fallback: %s", e)
            main = _build_fallback_profile(
                state.get("character_name") or "",
                state.get("character_description") or "",
            )
            ip_result = {
                "character_profiles": [main],
                "character_vis_map": {"#CHAR_01": main["visual_identity_string"]},
                "main_profile": main,
                "supporting_profiles": [],
            }
    else:
        # No script yet — use user hints
        main = _build_fallback_profile(
            state.get("character_name") or "",
            state.get("character_description") or "",
        )
        ip_result = {
            "character_profiles": [main],
            "character_vis_map": {"#CHAR_01": main["visual_identity_string"]},
            "main_profile": main,
            "supporting_profiles": [],
        }

    profiles = ip_result["character_profiles"]
    character_vis_map = ip_result["character_vis_map"]

    await publish_event(project_id, {
        "type": "agent_start",
        "agent": "character_designer",
        "character_count": len(profiles),
        "message": f"Xác định {len(profiles)} nhân vật — đang tạo ảnh...",
    })

    # Stage 5: Delete old characters, generate new ones concurrently
    from sqlalchemy import delete
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Character).where(Character.project_id == uuid.UUID(project_id)))
        await db.commit()

    from ...tasks.character_tasks import _generate_character_image_async
    if profiles:
        await asyncio.gather(*[
            _generate_character_image_async(project_id, p) for p in profiles
        ])
    else:
        # 0 characters (narration-only script) — skip generation
        logger.info("No characters found in script — narration-only video")

    from ...tasks.character_tasks import _load_characters
    characters = await _load_characters(project_id)

    await publish_event(project_id, {
        "type": "agent_done",
        "agent": "character_designer",
        "character_count": len(characters),
        "message": f"Đã thiết kế {len(characters)} nhân vật. Kiểm tra và duyệt.",
    })

    return {
        "extracted_characters": profiles,
        "character_profiles": profiles,
        "character_vis_map": character_vis_map,
        "character_count": len(characters),
        "characters": characters,
        "error": None,
        "current_stage": "character_review",
    }


async def character_review_node(state: ProductionState) -> dict:
    """
    Human-in-the-loop review of N character designs.
    Email: "Approve All / Regenerate" buttons.
    Dashboard: user can customize + regenerate individual characters, then approve all.
    """
    project_id = state["project_id"]
    characters = state.get("characters", [])
    n = len(characters)

    await publish_event(project_id, {
        "type": "agent_interrupt",
        "step": "character_review",
        "characters": characters,
        "character_count": n,
        "message": f"Đã thiết kế {n} nhân vật. Kiểm tra và duyệt.",
    })

    # Get project title for email
    project_title = "Du an moi"
    try:
        pid = uuid.UUID(project_id)
        async with AsyncSessionLocal() as db:
            proj = await db.get(Project, pid)
            if proj:
                project_title = proj.title or "Du an moi"
    except Exception:
        pass

    extra = (
        f"{n} nhan vat da duoc thiet ke theo chuan IP Character. "
        "Nhan 'Duyet Tat Ca' de tien hanh phan canh, hoac vao Dashboard de chinh sua tung nhan vat."
    )
    try:
        await send_approval_request(
            project_id=project_id,
            project_title=project_title,
            step="character_review",
            extra_info=extra,
        )
    except Exception as e:
        logger.warning("Email notification failed (character_review): %s", e)

    decision: dict = interrupt({
        "step": "character_review",
        "characters": characters,
    })

    approved: bool = decision.get("approved", False)

    if approved:
        await _mark_all_characters_approved(project_id)
        # Rebuild vis_map from DB (in case user regenerated characters while waiting)
        from ...tasks.character_tasks import _load_characters
        from ...services.r2_service import public_url
        fresh_chars = await _load_characters(project_id)
        vis_map = {
            c["ref_id"]: c["visual_identity_string"]
            for c in fresh_chars
            if c.get("ref_id") and c.get("visual_identity_string")
        }
    else:
        vis_map = {}

    return {
        "character_approved": approved,
        "character_vis_map": vis_map if approved else state.get("character_vis_map", {}),
        "approval_status": "approved" if approved else "rejected",
        "current_stage": "scene_planner" if approved else "character_designer",
    }


def route_after_character_review(state: ProductionState) -> str:
    """approved → scene_planner; rejected → character_designer (regenerate all)."""
    return "scene_planner" if state.get("character_approved") else "character_designer"


async def _mark_all_characters_approved(project_id: str) -> None:
    """Mark all characters for this project as approved and update project status."""
    pid = uuid.UUID(project_id)
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        chars = await db.execute(select(Character).where(Character.project_id == pid))
        for char in chars.scalars().all():
            char.is_selected = True
        proj = await db.get(Project, pid)
        if proj:
            proj.status = ProjectStatus.character_selected
        await db.commit()
