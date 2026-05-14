"""Agent Scene Planner — phân cảnh từ kịch bản. Không có interrupt — auto-advance."""
from __future__ import annotations
import logging
import uuid

from ...services.sse_service import publish_event
from ..state import ProductionState

logger = logging.getLogger(__name__)


async def scene_planner_node(state: ProductionState) -> dict:
    """
    Agent Scene Planner:
    1. Gọi POST /scenes/generate (reuse existing API logic)
    2. Trả về danh sách cảnh để frontend hiển thị
    3. Publish SSE event
    """
    project_id = state["project_id"]

    await publish_event(project_id, {
        "type": "agent_start",
        "agent": "scene_planner",
        "message": "Đang phân tích kịch bản thành cảnh quay...",
    })

    # Gọi scenes generate API nội bộ (tránh duplicate logic)
    from ...database import AsyncSessionLocal
    from ...models.scene import Scene
    from sqlalchemy import select

    try:
        from ...api.v1.scenes import _generate_scene_prompts, _scene_to_dict
        from ...models.project import Project
        from ...models.script import Script
        from sqlalchemy import delete

        async with AsyncSessionLocal() as db:
            pid = uuid.UUID(project_id)
            proj = await db.get(Project, pid)
            if not proj:
                return {"error": "Project not found", "current_stage": "scene_planner"}

            script_result = await db.execute(
                select(Script).where(Script.project_id == pid).order_by(Script.version.desc())
            )
            script = script_result.scalars().first()
            if not script:
                return {"error": "Cần viết kịch bản trước", "current_stage": "scene_planner"}

            scene_data = await _generate_scene_prompts(
                script=script,
                project=proj,
                character_description=state.get("character_description") or "",
                vis_map=state.get("character_vis_map") or {},
            )

            # Xóa cũ và lưu mới
            await db.execute(delete(Scene).where(Scene.project_id == pid))
            scenes_saved = []
            from ...models.scene import SceneStatus
            from ...models.project import ProjectStatus
            for i, s in enumerate(scene_data):
                scene = Scene(
                    project_id=pid,
                    scene_number=i + 1,
                    title=s.get("title", f"Cảnh {i + 1}"),
                    description=s.get("description", ""),
                    video_prompt=s.get("video_prompt", ""),
                    duration_seconds=s.get("duration_seconds", 10),
                    status=SceneStatus.pending,
                    characters_in_scene=s.get("characters_in_scene") or [],
                )
                db.add(scene)
                scenes_saved.append(scene)
            proj.status = ProjectStatus.scenes_ready
            await db.commit()
            for s in scenes_saved:
                await db.refresh(s)

            # Build plain-dict scenes (no enum objects) — avoids LangGraph checkpointer issues
            scenes_out = [
                {
                    "id": str(s.id),
                    "scene_number": s.scene_number,
                    "title": s.title or f"Cảnh {s.scene_number}",
                    "description": s.description or "",
                    "video_prompt": s.video_prompt or "",
                    "duration_seconds": s.duration_seconds or 10,
                    "characters_in_scene": s.characters_in_scene or [],
                }
                for s in scenes_saved
            ]

    except Exception as e:
        logger.error("scene_planner_node error: %s", e)
        await publish_event(project_id, {"type": "agent_error", "agent": "scene_planner", "error": str(e)})
        return {"error": str(e), "scenes": [], "current_stage": "scene_planner"}

    await publish_event(project_id, {
        "type": "agent_done",
        "agent": "scene_planner",
        "scene_count": len(scenes_out),
        "message": f"Đã phân {len(scenes_out)} cảnh. Kiểm tra và chỉnh sửa prompt.",
    })

    return {
        "scenes": scenes_out,
        "error": None,
        "current_stage": "scene_review",
    }


async def scene_review_node(state: ProductionState) -> dict:
    """Auto-approve: no interrupt. Query DB directly to avoid state deserialization issues."""
    project_id = state["project_id"]

    # Query DB — never trust state["scenes"] which may have stale/corrupt data
    has_scenes = await _scenes_exist_in_db(project_id)

    if not has_scenes:
        logger.warning("scene_review: no scenes in DB — retrying scene_planner")
        await publish_event(project_id, {
            "type": "agent_start",
            "agent": "scene_planner",
            "message": "Phân cảnh gặp lỗi — đang thử lại...",
        })
        return {"approval_status": "rejected", "current_stage": "scene_planner"}

    return {
        "approval_status": "approved",
        "current_stage": "cinematic_decomposer",
        "paused_at": None,
    }


async def _scenes_exist_in_db(project_id: str) -> bool:
    """Return True if any scenes exist in DB for this project."""
    try:
        from ...database import AsyncSessionLocal
        from ...models.scene import Scene
        from sqlalchemy import select, func

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(func.count()).select_from(Scene).where(
                    Scene.project_id == uuid.UUID(project_id)
                )
            )
            count = result.scalar()
            return (count or 0) > 0
    except Exception as e:
        logger.warning("_scenes_exist_in_db error: %s", e)
        return False


def route_after_scene_review(state: ProductionState) -> str:
    return "video_editor" if state.get("approval_status") == "approved" else "scene_planner"
