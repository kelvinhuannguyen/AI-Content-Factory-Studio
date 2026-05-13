"""Pipeline API — khởi động và điều khiển LangGraph Multi-Agent workflow."""
from __future__ import annotations
import uuid
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from langgraph.types import Command

from ...database import get_db
from ...models.project import Project
from ...langgraph.graph import get_graph
from ...langgraph.state import initial_state
from ...langgraph.checkpointer import get_thread_config

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _pipeline_response(graph_state) -> dict:
    """Chuẩn hoá response từ graph state snapshot."""
    values = graph_state.values if hasattr(graph_state, "values") else {}
    next_nodes = list(graph_state.next) if hasattr(graph_state, "next") and graph_state.next else []

    # Xác định trạng thái paused/running/done
    is_done = len(next_nodes) == 0
    is_paused = any("review" in n for n in next_nodes)
    status = "completed" if is_done else ("paused" if is_paused else "running")

    paused_at = None
    if is_paused:
        paused_at = next((n for n in next_nodes if "review" in n), None)

    return {
        "status": status,
        "paused_at": paused_at,
        "next_nodes": next_nodes,
        "current_stage": values.get("current_stage"),
        "script_id": values.get("script_id"),
        "characters": values.get("characters", []),
        "selected_character_id": values.get("selected_character_id"),
        "approval_status": values.get("approval_status"),
        "error": values.get("error"),
    }


async def _get_project_or_404(project_id: uuid.UUID, db: AsyncSession) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    return project


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/{project_id}/start", status_code=202)
async def start_pipeline(project_id: uuid.UUID, body: Optional[dict] = Body(default=None), db: AsyncSession = Depends(get_db)):
    """
    Khởi động LangGraph pipeline cho một project.
    Graph chạy từ screenwriter_node → interrupt tại script_review.
    Body (optional): { character_description?: str, character_name?: str }
    """
    project = await _get_project_or_404(project_id, db)

    graph = await get_graph()
    config = get_thread_config(str(project_id))

    # Kiểm tra nếu đã có checkpoint (pipeline đang chạy)
    existing = await graph.aget_state(config)
    if existing and existing.values:
        raise HTTPException(409, "Pipeline đã chạy. Dùng /resume để tiếp tục hoặc /state để xem trạng thái.")

    body = body or {}
    character_description = body.get("character_description", "")
    character_name = body.get("character_name", "")

    # Tạo initial state từ project
    state = initial_state(
        project_id=str(project_id),
        production_type=project.production_type.value if hasattr(project.production_type, 'value') else str(project.production_type),
        topic=project.topic or "",
        genre=project.genre or "",
        style=project.style or "",
        duration_seconds=project.duration_seconds or 60,
        language=project.preferred_language or "vi",
        character_description=character_description,
        character_name=character_name,
    )

    # Chạy graph (sẽ dừng tại interrupt đầu tiên trong script_review_node)
    try:
        result = await graph.ainvoke(state, config=config)
        final_state = await graph.aget_state(config)
        return _pipeline_response(final_state)
    except Exception as e:
        logger.error("Pipeline start error for %s: %s", project_id, e)
        raise HTTPException(500, f"Pipeline error: {e}")


@router.post("/{project_id}/resume")
async def resume_pipeline(
    project_id: uuid.UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """
    Tiếp tục graph sau khi user duyệt / từ chối tại điểm dừng.

    Body cho script_review:
        { "step": "script", "approved": true }
        { "step": "script", "approved": false, "notes": "Cần thêm kịch tính" }

    Body cho character_review:
        { "step": "character", "approved": true, "selected_character_id": "uuid" }
    """
    await _get_project_or_404(project_id, db)

    graph = await get_graph()
    config = get_thread_config(str(project_id))

    step = body.get("step", "")
    approved = bool(body.get("approved", False))

    if step == "script":
        resume_value = {
            "approved": approved,
            "notes": body.get("notes", "") if not approved else "",
        }
    elif step == "character":
        resume_value = {
            "approved": approved,
            "selected_character_id": body.get("selected_character_id", ""),
        }
    elif step == "scene":
        resume_value = {
            "approved": approved,
        }
    else:
        raise HTTPException(422, f"Unknown step '{step}'. Valid: 'script', 'character', 'scene'")

    try:
        await graph.ainvoke(Command(resume=resume_value), config=config)
        final_state = await graph.aget_state(config)
        return _pipeline_response(final_state)
    except Exception as e:
        logger.error("Pipeline resume error for %s: %s", project_id, e)
        raise HTTPException(500, f"Pipeline resume error: {e}")


@router.get("/{project_id}/state")
async def get_pipeline_state(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Lấy trạng thái hiện tại của LangGraph pipeline từ Redis checkpoint.
    Dùng để frontend đồng bộ UI khi reload trang.
    """
    await _get_project_or_404(project_id, db)

    try:
        graph = await get_graph()
        config = get_thread_config(str(project_id))
        state = await graph.aget_state(config)
        if not state or not state.values:
            return {"status": "not_started", "current_stage": None, "paused_at": None}
        return _pipeline_response(state)
    except Exception as e:
        logger.error("Pipeline state error for %s: %s", project_id, e)
        return {"status": "not_started", "current_stage": None, "paused_at": None, "langgraph_error": str(e)}


@router.delete("/{project_id}/reset", status_code=204)
async def reset_pipeline(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Xóa checkpoint Redis — cho phép restart pipeline từ đầu.
    Hữu ích khi project bị lỗi hoặc user muốn làm lại toàn bộ.
    """
    await _get_project_or_404(project_id, db)

    graph = await get_graph()
    config = get_thread_config(str(project_id))

    # Ghi đè checkpoint bằng state rỗng
    try:
        from langgraph.checkpoint.base import empty_checkpoint
        await graph.checkpointer.aput(config, empty_checkpoint(), {}, {})
    except Exception as e:
        logger.warning("Could not reset checkpoint: %s", e)
