"""Agent Character Designer — trigger Celery để tạo ảnh + điểm dừng chọn nhân vật."""
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

_POLL_INTERVAL = 5    # giây
_POLL_TIMEOUT  = 300  # 5 phút max


async def character_designer_node(state: ProductionState) -> dict:
    """
    Agent Character Designer:
    1. Trigger Celery task generate_character_variants (reuse existing task)
    2. Poll DB mỗi 5s cho đến khi đủ 3 characters hoàn thành
    3. Update Project.status → character_selected (stage xong)
    4. Publish SSE event
    """
    project_id = state["project_id"]
    description = state.get("character_description") or "Nhân vật chính phù hợp với nội dung video"
    name = state.get("character_name") or ""

    await publish_event(project_id, {
        "type": "agent_start",
        "agent": "character_designer",
        "message": "Đang khởi tạo tạo nhân vật...",
    })

    # Generate characters directly (no Celery worker needed — runs inline in BackgroundTask)
    try:
        from ...tasks.character_tasks import _generate_variants_async
        await _generate_variants_async(None, project_id, description, name, None)
        logger.info("Character generation complete for project %s", project_id)
    except Exception as e:
        logger.error("Character generation failed: %s", e)
        await publish_event(project_id, {"type": "agent_error", "agent": "character_designer", "error": str(e)})
        return {"error": str(e), "current_stage": "character_designer"}

    # Query DB for the generated characters (with R2 URLs)
    characters = await _wait_for_characters(project_id)

    if not characters:
        err = "Hết thời gian chờ tạo nhân vật (>5 phút)"
        await publish_event(project_id, {"type": "agent_error", "agent": "character_designer", "error": err})
        return {"error": err, "current_stage": "character_designer"}

    await publish_event(project_id, {
        "type": "agent_done",
        "agent": "character_designer",
        "characters": characters,
        "message": f"Đã tạo {len(characters)} biến thể nhân vật. Vui lòng chọn 1 biến thể.",
    })

    return {
        "characters": characters,
        "error": None,
        "current_stage": "character_review",
    }


async def character_review_node(state: ProductionState) -> dict:
    """
    Điểm dừng chọn nhân vật:
    - Gửi email Gmail thông báo nhân vật đã tạo xong
    - Email Approve → tự động chọn biến thể 1 (variant_index=0)
    - Email Reject → huỷ, tạo lại
    - GUI: user chọn biến thể bất kỳ qua POST /pipeline/{id}/resume
    """
    project_id = state["project_id"]
    characters = state.get("characters", [])
    n = len(characters)

    await publish_event(project_id, {
        "type": "agent_interrupt",
        "step": "character_review",
        "characters": characters,
        "message": f"Da tao {n} bien the nhan vat. Da gui email duyet.",
    })

    # Lấy project title
    project_title = "Du an moi"
    try:
        pid = uuid.UUID(project_id)
        async with AsyncSessionLocal() as db:
            proj = await db.get(Project, pid)
            if proj:
                project_title = proj.title or "Du an moi"
    except Exception:
        pass

    # Gửi email — Approve sẽ tự chọn variant 0, Reject tạo lại
    extra = (
        f"{n} bien the nhan vat da san sang. "
        "Nhan Duyet de chon bien the 1 (mac dinh) hoac vao Dashboard de chon tu tay."
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

    selected_id: str = decision.get("selected_character_id", "")
    approved: bool = bool(selected_id) or decision.get("approved", False)

    # Nếu approve qua email (không có selected_character_id) → auto-select variant 0
    if approved and not selected_id and characters:
        selected_id = characters[0].get("id", "")

    if approved and selected_id:
        # Mark selected in DB + update project status
        await _mark_character_selected(state["project_id"], selected_id)

    return {
        "selected_character_id": selected_id if approved else None,
        "character_approved": approved,
        "approval_status": "approved" if approved else "rejected",
        "current_stage": "done" if approved else "character_designer",
    }


async def _wait_for_characters(project_id: str) -> list[dict]:
    """Poll DB until 3 characters with image_r2_key exist (or timeout)."""
    waited = 0
    pid = uuid.UUID(project_id)
    while waited < _POLL_TIMEOUT:
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            result = await db.execute(
                select(Character)
                .where(Character.project_id == pid, Character.image_r2_key.isnot(None))
                .order_by(Character.variant_index)
            )
            chars = result.scalars().all()
            if len(chars) >= 3:
                from ...services.r2_service import public_url, generate_presigned_url
                out = []
                for c in chars[:3]:
                    url = public_url(c.image_r2_key)
                    if url is None and c.image_r2_key:
                        try:
                            url = await generate_presigned_url(c.image_r2_key)
                        except Exception:
                            url = None
                    out.append({
                        "id": str(c.id),
                        "variant_index": c.variant_index,
                        "image_r2_key": c.image_r2_key,
                        "image_url": url,
                        "name": c.name,
                        "description": c.description,
                    })
                return out
        await asyncio.sleep(_POLL_INTERVAL)
        waited += _POLL_INTERVAL
    return []


async def _mark_character_selected(project_id: str, character_id: str) -> None:
    """Mark selected character in DB and update project status."""
    pid = uuid.UUID(project_id)
    cid = uuid.UUID(character_id)
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        chars = await db.execute(select(Character).where(Character.project_id == pid))
        for char in chars.scalars().all():
            char.is_selected = (char.id == cid)
        proj = await db.get(Project, pid)
        if proj:
            proj.status = ProjectStatus.character_selected
        await db.commit()
