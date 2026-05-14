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
from fastapi import APIRouter, BackgroundTasks, Query
from fastapi.responses import HTMLResponse

from ...services.notification_service import resolve_token

router = APIRouter()
logger = logging.getLogger(__name__)


_resume_locks: set[str] = set()  # prevent concurrent resume on same project


async def _do_resume(project_id: str, step: str, action: str, approved: bool, package: str = "a") -> None:
    """Run LangGraph resume in background — avoids browser timeout on slow nodes."""
    if project_id in _resume_locks:
        logger.warning("Resume already in progress for project %s — skipping duplicate", project_id)
        return
    _resume_locks.add(project_id)
    try:
        resume_value = await _build_resume_value(step, approved, project_id, action, package)
        from ...langgraph.graph import get_graph
        from ...langgraph.checkpointer import get_thread_config
        from langgraph.types import Command
        graph  = await get_graph()
        config = get_thread_config(project_id)
        state  = await graph.aget_state(config)
        if state and state.next:
            await graph.ainvoke(Command(resume=resume_value), config=config)
            logger.info("LangGraph resumed: project=%s step=%s action=%s", project_id, step, action)
        else:
            logger.info("LangGraph not paused for project %s — skipping resume", project_id)
    except Exception as e:
        logger.warning("LangGraph resume error (non-fatal): %s", e)
    finally:
        _resume_locks.discard(project_id)


def _action_html(action: str, step: str) -> HTMLResponse:
    responses = {
        "proceed": ("Đã duyệt — Tiếp tục",   "✅", "#16a34a", "Pipeline tiếp tục tự động. Bạn có thể đóng trang này."),
        "remake":  ("Yêu cầu làm lại",         "🔄", "#d97706", "Hệ thống sẽ tạo lại video. Bạn có thể đóng trang này."),
        "hold":    ("Đã tạm dừng",             "⏸", "#52525b", "Project ở trạng thái hold. Vào dashboard để tiếp tục."),
        "approve": ("Đã duyệt thành công",     "✅", "#16a34a", f"<strong>{_step_label(step)}</strong> đã được duyệt.<br>Pipeline tự động tiếp tục."),
        "reject":  ("Đã từ chối",              "❌", "#dc2626", f"<strong>{_step_label(step)}</strong> bị từ chối.<br>Hệ thống sẽ tạo lại."),
    }
    title, emoji, color, body = responses.get(action, ("Hoàn thành", "✅", "#16a34a", ""))
    return HTMLResponse(content=_html_page(title, emoji, body, color))


@router.get("/{token}")
async def process_approval_via_link(
    token: str,
    background_tasks: BackgroundTasks,
    action: str = Query(..., pattern="^(approve|reject|proceed|remake|hold)$"),
    package: str = Query(default="a", pattern="^[ab]$"),
):
    """
    Endpoint được gọi khi user click link trong email (GET request).
    Token single-use, hết hạn 48h. LangGraph resume chạy trong background.
    """
    payload = await resolve_token(token)
    if not payload:
        return HTMLResponse(
            status_code=404,
            content=_html_page(
                "Link đã hết hạn", "❌",
                "Link này đã được dùng hoặc đã hết hạn (48 giờ).<br>"
                "Vào dashboard để thực hiện thủ công.",
                "#dc2626",
            ),
        )

    project_id = payload["project_id"]
    step       = payload["step"]
    approved   = action in ("approve", "proceed")

    logger.info("Email approval: project=%s step=%s action=%s package=%s", project_id, step, action, package)

    # Resume chạy background — tránh browser timeout khi node mất nhiều phút
    background_tasks.add_task(_do_resume, project_id, step, action, approved, package)

    return _action_html(action, step)


@router.post("/{token}")
async def process_approval_api(
    token: str,
    background_tasks: BackgroundTasks,
    action: str = Query(..., pattern="^(approve|reject|proceed|remake|hold)$"),
    package: str = Query(default="a", pattern="^[ab]$"),
):
    """Programmatic approval (frontend wizard, Telegram). Same logic as GET."""
    payload = await resolve_token(token)
    if not payload:
        return HTMLResponse(
            status_code=404,
            content=_html_page("Token không hợp lệ", "❌",
                "Link này đã được dùng hoặc đã hết hạn (48 giờ).", "#dc2626"),
        )

    project_id = payload["project_id"]
    step       = payload["step"]
    approved   = action in ("approve", "proceed")

    logger.info("API approval: project=%s step=%s action=%s package=%s", project_id, step, action, package)
    background_tasks.add_task(_do_resume, project_id, step, action, approved, package)

    return _action_html(action, step)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _build_resume_value(step: str, approved: bool, project_id: str, action: str = "approve", package: str = "a") -> dict:
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
        # All characters approved together — no single selection
        return {"approved": approved}

    if step == "scene_review":
        return {"approved": approved}

    if step == "shot_review":
        return {"approved": approved}

    if step == "quality_review":
        return {
            "approved": approved,
            "notes": "" if approved else "Tu choi qua email",
        }

    if step == "video_review":
        # action is one of: proceed, remake, hold
        return {"action": action}

    if step == "seo_review":
        return {"approved": approved, "selected_package": package}

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
        "character_review": "Duyệt Nhân Vật (Trạm 1)",
        "shot_review":      "Duyệt Storyboard (Trạm 2)",
        "seo_review":       "Duyệt Final Master (Trạm 3)",
        "script_review":    "Duyệt Kịch Bản",
        "scene_review":     "Duyệt Phân Cảnh",
        "quality_review":   "Duyệt Chất Lượng",
        "video_review":     "Duyệt Video Final",
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
