"""Trạm 2 — Storyboard & Shot List interrupt.

Fires after cinematic_decomposer generates 8s shots.
User reviews shot prompts before bulk render (saves cost).
Approved → continuity_director; Rejected → scene_planner (re-plan).
"""
from __future__ import annotations
import logging
import uuid

from langgraph.types import interrupt

from ...services.sse_service import publish_event
from ..state import ProductionState

logger = logging.getLogger(__name__)


async def shot_review_node(state: ProductionState) -> dict:
    """
    Trạm 2: Human reviews 8s shot prompts before bulk video render.
    - Loads shots from DB, publishes SSE interrupt
    - Sends email with shot list preview + Approve/Reject buttons
    - interrupt() pauses graph, waits for resume
    """
    project_id = state["project_id"]

    # Load shots from DB
    shots = await _load_shots(project_id)
    shot_count = len(shots)
    scene_count = len({(s.get("shot_id") or "")[:4] for s in shots if s.get("shot_id")})

    await publish_event(project_id, {
        "type": "agent_interrupt",
        "step": "shot_review",
        "shot_count": shot_count,
        "scene_count": scene_count,
        "message": f"{shot_count} shots sẵn sàng để duyệt trước khi render.",
    })

    # Send email
    project = await _get_project(project_id)
    if project:
        try:
            from ...services.notification_service import send_shot_review_request
            await send_shot_review_request(project_id, project.title or "Dự án mới", shots)
        except Exception as e:
            logger.warning("Shot review email failed: %s", e)

    decision: dict = interrupt({
        "step": "shot_review",
        "shot_count": shot_count,
        "project_id": project_id,
    })

    approved: bool = decision.get("approved", True)
    return {
        "approval_status": "approved" if approved else "rejected",
        "current_stage": "shot_review",
        "paused_at": None,
    }


def route_after_shot_review(state: ProductionState) -> str:
    """approved → continuity_director; rejected → scene_planner."""
    return "continuity_director" if state.get("approval_status") == "approved" else "scene_planner"


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _load_shots(project_id: str) -> list[dict]:
    """Load shots from DB, return as list of dicts."""
    try:
        from ...database import AsyncSessionLocal
        from ...models.shot import Shot
        from sqlalchemy import select

        pid = uuid.UUID(project_id)
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Shot)
                .where(Shot.project_id == pid)
                .order_by(Shot.shot_id)
            )
            shots = result.scalars().all()
            return [
                {
                    "shot_id": s.shot_id,
                    "duration": s.duration,
                    "prompt": s.prompt,
                    "qc_score": s.qc_score,
                }
                for s in shots
            ]
    except Exception as e:
        logger.warning("_load_shots error: %s", e)
        return []


async def _get_project(project_id: str):
    """Fetch project from DB."""
    try:
        from ...database import AsyncSessionLocal
        from ...models.project import Project

        pid = uuid.UUID(project_id)
        async with AsyncSessionLocal() as db:
            return await db.get(Project, pid)
    except Exception:
        return None
