"""Generation API — SSE stream + pipeline launch."""
import uuid
import logging
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ...database import get_db
from ...models.generation_task import GenerationTask
from ...services.sse_service import stream_events

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{project_id}/stream")
async def sse_stream(project_id: uuid.UUID):
    """
    Server-Sent Events stream for all generation progress in a project.
    Celery tasks publish via Redis; browser subscribes here.
    """
    return StreamingResponse(
        stream_events(str(project_id)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{project_id}/tasks")
async def get_tasks(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """List generation tasks for a project (for queue monitor)."""
    result = await db.execute(
        select(GenerationTask)
        .where(GenerationTask.project_id == project_id)
        .order_by(GenerationTask.created_at.desc())
    )
    tasks = result.scalars().all()
    return [_task_to_dict(t) for t in tasks]


@router.post("/start")
async def start_generation(body: dict):
    return {"status": "not_implemented", "message": "Sprint 5: Full pipeline launch"}


@router.post("/tasks/{task_id}/retry")
async def retry_task(task_id: str):
    return {"status": "not_implemented", "message": "Sprint 5: Per-task retry"}


@router.delete("/{project_id}/cancel")
async def cancel_generation(project_id: str):
    return {"status": "not_implemented", "message": "Sprint 5: Cancel pipeline"}


def _task_to_dict(t: GenerationTask) -> dict:
    return {
        "id": str(t.id),
        "project_id": str(t.project_id),
        "scene_id": str(t.scene_id) if t.scene_id else None,
        "task_type": t.task_type,
        "status": t.status,
        "progress_pct": t.progress_pct,
        "result_r2_key": t.result_r2_key,
        "error_message": t.error_message,
        "attempts": t.attempts,
        "created_at": t.created_at.isoformat(),
    }
