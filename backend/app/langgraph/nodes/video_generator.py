"""Agent Video Generator — trigger Celery chord pipeline."""
from __future__ import annotations
import logging

from ...services.sse_service import publish_event
from ..state import ProductionState

logger = logging.getLogger(__name__)


async def video_generator_node(state: ProductionState) -> dict:
    """
    Agent Video Generator:
    1. Launch pipeline_tasks.launch_production_pipeline (Celery chord)
    2. Frontend theo dõi tiến độ qua SSE stream (task events từ Celery tasks)
    3. Node này trả về ngay — không chờ Celery hoàn thành (non-blocking)
    """
    project_id = state["project_id"]

    await publish_event(project_id, {
        "type": "agent_start",
        "agent": "video_generator",
        "message": "Khởi động pipeline tạo video (Celery chord)...",
    })

    # Selected music track (nếu có)
    music_key: str | None = None

    try:
        from ...tasks.pipeline_tasks import launch_production_pipeline
        launch_production_pipeline.apply_async(
            kwargs={"project_id": project_id, "music_key": music_key},
            queue="cpu_queue",
        )
        logger.info("Production pipeline launched via LangGraph for project %s", project_id)
    except Exception as e:
        logger.error("Failed to launch pipeline: %s", e)
        await publish_event(project_id, {"type": "agent_error", "agent": "video_generator", "error": str(e)})
        return {"error": str(e), "current_stage": "video_generator"}

    await publish_event(project_id, {
        "type": "agent_done",
        "agent": "video_generator",
        "message": "Pipeline đang chạy. Theo dõi tiến độ trong tab Generation.",
    })

    return {
        "error": None,
        "current_stage": "generating",
        "approval_status": "pending",
    }
