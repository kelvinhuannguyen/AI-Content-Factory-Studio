"""Approvals API — public token endpoint cho email/Telegram deep links.

Mỗi bước có resume payload riêng:
  script_review    → {approved, notes}
  character_review → {approved, selected_character_id}  # auto-select variant 0 nếu approve
  scene_review     → {approved}
  quality_review   → {approved, notes}
  seo_review       → {approved}
"""
import logging
import uuid
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse

from ...services.notification_service import resolve_token

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/{token}")
async def process_approval(
    token: str,
    action: str = Query(..., pattern="^(approve|reject|proceed|remake|hold)$"),
):
    """
    Được gọi từ nút trong email hoặc Telegram inline button.
    Token single-use, hết hạn 48h.
    Resume LangGraph với payload phù hợp từng bước.
    """
    payload = await resolve_token(token)
    if not payload:
        return HTMLResponse(
            status_code=404,
            content=_html_page(
                "Token không hợp lệ", "❌",
                "Link này đã được dùng hoặc đã hết hạn (48 giờ).",
                "#dc2626",
            ),
        )

    project_id = payload["project_id"]
    step       = payload["step"]
    approved   = action in ("approve", "proceed")

    logger.info("Approval: project=%s step=%s action=%s", project_id, step, action)

    # Build resume value tuỳ theo bước
    resume_value = await _build_resume_value(step, approved, project_id)

    # Resume LangGraph nếu graph đang pause
    try:
        from ...langgraph.graph import get_graph
        from ...langgraph.checkpointer import get_thread_config
        from langgraph.types import Command

        graph  = await get_graph()
        config = get_thread_config(project_id)
        state  = await graph.aget_state(config)

        if state and state.next:
            await graph.ainvoke(Command(resume=resume_value), config=config)
            logger.info("LangGraph resumed: project=%s step=%s approved=%s", project_id, step, approved)
        else:
            logger.info("LangGraph not paused for project %s — skipping resume", project_id)
    except Exception as e:
        logger.warning("LangGraph resume error (non-fatal): %s", e)

    # HTML response — hiển thị trong browser khi click link
    _action_responses = {
        "proceed": ("Đã duyệt — Tiếp tục", "✅", "#16a34a", "Pipeline tiếp tục tự động sang bước SEO."),
        "remake":  ("Làm lại video", "🔄", "#d97706", "Hệ thống sẽ tạo lại video với chất lượng cao hơn."),
        "hold":    ("Tạm dừng", "⏸", "#64748b", "Project đang ở trạng thái hold. Bạn có thể tiếp tục sau."),
        "approve": ("Đã duyệt thành công", "✅", "#16a34a", f"Bước <strong>{_step_label(step)}</strong> đã được duyệt."),
        "reject":  ("Đã từ chối", "❌", "#dc2626", f"Bước <strong>{_step_label(step)}</strong> bị từ chối."),
    }
    title, emoji, color, body = _action_responses.get(action, ("Hoàn thành", "✅", "#16a34a", ""))
    return HTMLResponse(content=_html_page(title, emoji, body, color))


@router.get("/{token}")
async def get_approval_status(token: str):
    """Kiểm tra token có còn hợp lệ không (không consume)."""
    from ...redis_client import get_redis
    import json
    redis = await get_redis()
    raw = await redis.get(f"approval:{token}")
    if not raw:
        raise HTTPException(404, "Token không hợp lệ hoặc đã hết hạn")
    data = json.loads(raw)
    ttl  = await redis.ttl(f"approval:{token}")
    return {**data, "ttl_seconds": ttl}


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _build_resume_value(step: str, approved: bool, project_id: str) -> dict:
    """
    Trả về resume dict phù hợp với từng interrupt node.

    script_review:    {approved, notes}
    character_review: {approved, selected_character_id}  ← auto-select variant 0 nếu approve
    scene_review:     {approved}
    quality_review:   {approved, notes}
    seo_review:       {approved}
    """
    if step == "script_review":
        return {
            "approved": approved,
            "notes": "" if approved else "Tu choi qua email",
        }

    if step == "character_review":
        selected_id = ""
        if approved:
            # Auto-select variant_index=0 (biến thể đầu tiên)
            selected_id = await _get_first_character_id(project_id)
        return {
            "approved": approved,
            "selected_character_id": selected_id,
        }

    if step == "scene_review":
        return {"approved": approved}

    if step == "quality_review":
        return {
            "approved": approved,
            "notes": "" if approved else "Tu choi qua email",
        }

    if step == "video_review":
        # action is one of: proceed, remake, hold
        return {"action": action}

    # seo_review và các bước khác
    return {"approved": approved}


async def _get_first_character_id(project_id: str) -> str:
    """Lấy character_id của variant_index=0 từ DB."""
    try:
        from ...database import AsyncSessionLocal
        from ...models.character import Character
        from sqlalchemy import select

        pid = uuid.UUID(project_id)
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Character)
                .where(Character.project_id == pid)
                .order_by(Character.variant_index)
                .limit(1)
            )
            char = result.scalars().first()
            return str(char.id) if char else ""
    except Exception as e:
        logger.warning("Could not fetch first character: %s", e)
        return ""


def _step_label(step: str) -> str:
    return {
        "script_review":    "Duyệt Kịch Bản",
        "character_review": "Duyệt Nhân Vật",
        "scene_review":     "Duyệt Phân Cảnh",
        "quality_review":   "Duyệt Chất Lượng",
        "video_review":     "Duyệt Video Final",
        "seo_review":       "Duyệt Gói SEO",
    }.get(step, step)


def _html_page(title: str, emoji: str, body: str, color: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{title}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0 }}
    body {{
      font-family: system-ui, -apple-system, sans-serif;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      background: #f8fafc;
      padding: 24px;
    }}
    .card {{
      background: white;
      border-radius: 20px;
      padding: 48px 40px;
      text-align: center;
      box-shadow: 0 4px 32px rgba(0,0,0,.08);
      max-width: 420px;
      width: 100%;
    }}
    .emoji {{ font-size: 64px; line-height: 1; margin-bottom: 16px }}
    h1 {{ font-size: 22px; color: {color}; margin-bottom: 12px }}
    p {{ font-size: 15px; color: #64748b; line-height: 1.6 }}
    .hint {{ margin-top: 24px; font-size: 13px; color: #94a3b8 }}
  </style>
</head>
<body>
  <div class="card">
    <div class="emoji">{emoji}</div>
    <h1>{title}</h1>
    <p>{body}</p>
    <p class="hint">Bạn có thể đóng cửa sổ này.</p>
  </div>
</body>
</html>"""
