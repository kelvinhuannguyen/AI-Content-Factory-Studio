"""Agent Scene Planner — phân cảnh từ kịch bản + điểm dừng duyệt cảnh."""
from __future__ import annotations
import logging
import uuid

from langgraph.types import interrupt

from ...services.sse_service import publish_event
from ...services.notification_service import send_approval_request
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

            scenes_out = [_scene_to_dict(s) for s in scenes_saved]

    except Exception as e:
        logger.error("scene_planner_node error: %s", e)
        await publish_event(project_id, {"type": "agent_error", "agent": "scene_planner", "error": str(e)})
        # Return empty scenes — scene_review will not send email if scenes=[]
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
    """
    Điểm dừng duyệt cảnh:
    - Nếu scenes=[] (scene_planner bị lỗi) → tự động retry, không gửi email
    - Gửi email với số cảnh + tổng thời lượng
    - Duyệt → bắt đầu tạo video
    - Từ chối → phân cảnh lại
    """
    project_id = state["project_id"]
    scenes = state.get("scenes", [])
    n = len(scenes)

    # Auto-retry if scene_planner failed (no scenes) instead of prompting user
    if n == 0:
        logger.warning("scene_review: no scenes available — sending back to scene_planner")
        await publish_event(project_id, {
            "type": "agent_start",
            "agent": "scene_planner",
            "message": "Phân cảnh gặp lỗi — đang thử lại...",
        })
        return {"approval_status": "rejected", "current_stage": "scene_planner"}

    total_s = sum(s.get("duration_seconds", 0) for s in scenes)

    await publish_event(project_id, {
        "type": "agent_interrupt",
        "step": "scene_review",
        "scenes": scenes,
        "message": f"Da phan {n} canh ({total_s}s). Da gui email duyet.",
    })

    # Lấy project title
    project_title = "Du an moi"
    try:
        pid = uuid.UUID(project_id)
        from ...database import AsyncSessionLocal
        from ...models.project import Project
        async with AsyncSessionLocal() as db:
            proj = await db.get(Project, pid)
            if proj:
                project_title = proj.title or "Du an moi"
    except Exception:
        pass

    extra = f"{n} canh · Tong {total_s}s · Duyet de bat dau tao video (Kling-3-Pro + ElevenLabs)"
    try:
        await send_approval_request(
            project_id=project_id,
            project_title=project_title,
            step="scene_review",
            extra_info=extra,
        )
    except Exception as e:
        logger.warning("Email notification failed (scene_review): %s", e)

    decision: dict = interrupt({
        "step": "scene_review",
        "scenes": scenes,
    })

    approved: bool = decision.get("approved", False)
    return {
        "approval_status": "approved" if approved else "rejected",
        "current_stage": "video_editor" if approved else "scene_planner",
    }


def route_after_scene_review(state: ProductionState) -> str:
    return "video_editor" if state.get("approval_status") == "approved" else "scene_planner"
