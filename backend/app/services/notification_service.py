"""Notification service — Resend (primary) + Telegram (optional).

Approval flow:
  1. send_approval_request() → creates Redis token (48h) → sends email via Resend
  2. User clicks link in email → POST /approvals/{token}?action=approve|reject|proceed|remake|hold
  3. Token resolved → LangGraph resumed
"""
from __future__ import annotations
import json
import logging
import uuid
from datetime import datetime, timezone

import httpx

from ..config import get_settings
from ..redis_client import get_redis
from .resend_service import send_email_resend

logger = logging.getLogger(__name__)
settings = get_settings()

_TOKEN_TTL = 48 * 3600  # 48 hours

# ── Token management ──────────────────────────────────────────────────────────

async def create_approval_token(project_id: str, step: str) -> str:
    """Create single-use UUID token in Redis, expires 48h."""
    token = str(uuid.uuid4())
    redis = await get_redis()
    payload = json.dumps({
        "project_id": project_id,
        "step": step,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    await redis.setex(f"approval:{token}", _TOKEN_TTL, payload)
    return token


async def resolve_token(token: str) -> dict | None:
    """Consume token from Redis (single-use). Returns None if expired/missing."""
    redis = await get_redis()
    raw = await redis.get(f"approval:{token}")
    if not raw:
        return None
    await redis.delete(f"approval:{token}")
    return json.loads(raw)


# ── URL builders ──────────────────────────────────────────────────────────────

def _approval_url(token: str, action: str) -> str:
    return f"{settings.backend_url}/api/v1/approvals/{token}?action={action}"


# ── Telegram (optional) ───────────────────────────────────────────────────────

async def _send_telegram(text: str, buttons: list[dict]) -> None:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": {"inline_keyboard": [buttons]},
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json=payload,
            )
        if resp.status_code != 200:
            logger.warning("Telegram error %s: %s", resp.status_code, resp.text[:200])
    except Exception as e:
        logger.warning("Telegram error: %s", e)


# ── Email body builders ───────────────────────────────────────────────────────

_STEP_LABELS = {
    "script_review":    "Duyệt Kịch Bản",
    "character_review": "Duyệt Nhân Vật",
    "scene_review":     "Duyệt Phân Cảnh",
    "quality_review":   "Duyệt Chất Lượng Video",
    "video_review":     "Duyệt Video Final",
    "seo_review":       "Duyệt Gói SEO",
}


def _build_email_html(
    step_label: str, project_title: str, extra_info: str,
    approve_url: str, reject_url: str,
) -> str:
    return f"""<!DOCTYPE html>
<html lang="vi">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:20px;background:#f8fafc;font-family:system-ui,sans-serif">
<div style="max-width:560px;margin:auto;background:white;border-radius:16px;padding:32px;box-shadow:0 2px 16px rgba(0,0,0,.08)">
  <div style="text-align:center;margin-bottom:24px">
    <span style="font-size:40px">🎬</span>
    <h1 style="margin:8px 0 4px;font-size:22px;color:#1e293b">{step_label}</h1>
    <p style="margin:0;color:#64748b;font-size:14px">AI Content Factory Studio</p>
  </div>
  <div style="background:#f1f5f9;border-radius:10px;padding:16px;margin-bottom:24px">
    <p style="margin:0 0 4px;font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:.05em">Dự án</p>
    <p style="margin:0;font-size:16px;font-weight:600;color:#0f172a">{project_title}</p>
    {f'<p style="margin:8px 0 0;font-size:13px;color:#475569">{extra_info}</p>' if extra_info else ''}
  </div>
  <div style="display:flex;gap:12px;margin-bottom:24px">
    <a href="{approve_url}"
       style="flex:1;display:block;text-align:center;background:#16a34a;color:white;padding:14px;border-radius:10px;text-decoration:none;font-weight:700;font-size:15px">
      ✅ Duyệt
    </a>
    <a href="{reject_url}"
       style="flex:1;display:block;text-align:center;background:#dc2626;color:white;padding:14px;border-radius:10px;text-decoration:none;font-weight:700;font-size:15px">
      ❌ Từ chối
    </a>
  </div>
  <p style="margin:0;font-size:12px;color:#94a3b8;text-align:center">
    Link hết hạn sau 48 giờ · Chỉ dùng được 1 lần
  </p>
  <hr style="border:none;border-top:1px solid #e2e8f0;margin:16px 0">
  <p style="margin:0;font-size:11px;color:#cbd5e1;word-break:break-all">
    Approve: {approve_url}<br>Reject: {reject_url}
  </p>
</div>
</body></html>"""


def _build_video_review_html(
    project_title: str, ai_score: int, overall_score: int,
    proceed_url: str, remake_url: str, hold_url: str,
) -> str:
    score_color = "#16a34a" if overall_score >= 75 else "#d97706"
    status_text = "✓ Đạt ngưỡng chất lượng (≥75)" if overall_score >= 75 else "⚠ Chưa đạt ngưỡng (<75)"
    status_color = "#16a34a" if overall_score >= 75 else "#d97706"
    return f"""<!DOCTYPE html>
<html lang="vi">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:20px;background:#f8fafc;font-family:system-ui,sans-serif">
<div style="max-width:560px;margin:auto;background:white;border-radius:16px;padding:32px;box-shadow:0 2px 16px rgba(0,0,0,.08)">
  <div style="text-align:center;margin-bottom:24px">
    <span style="font-size:40px">🎬</span>
    <h1 style="margin:8px 0 4px;font-size:22px;color:#1e293b">Duyệt Video Final</h1>
    <p style="margin:0;color:#64748b;font-size:14px">AI Content Factory Studio</p>
  </div>
  <div style="background:#f1f5f9;border-radius:10px;padding:16px;margin-bottom:16px">
    <p style="margin:0 0 4px;font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:.05em">Dự án</p>
    <p style="margin:0;font-size:16px;font-weight:600;color:#0f172a">{project_title}</p>
  </div>
  <div style="text-align:center;background:#f8fafc;border-radius:10px;padding:16px;margin-bottom:24px">
    <div style="font-size:48px;font-weight:900;color:{score_color}">{overall_score}</div>
    <div style="font-size:14px;color:#64748b">/ 100 điểm · AI Score: {ai_score}/10</div>
    <div style="font-size:13px;margin-top:4px;color:{status_color}">{status_text}</div>
  </div>
  <div style="display:flex;gap:10px;margin-bottom:24px">
    <a href="{proceed_url}"
       style="flex:1;display:block;text-align:center;background:#16a34a;color:white;padding:14px 8px;border-radius:10px;text-decoration:none;font-weight:700;font-size:14px">
      ✅ Tiếp tục
    </a>
    <a href="{remake_url}"
       style="flex:1;display:block;text-align:center;background:#d97706;color:white;padding:14px 8px;border-radius:10px;text-decoration:none;font-weight:700;font-size:14px">
      🔄 Làm lại
    </a>
    <a href="{hold_url}"
       style="flex:1;display:block;text-align:center;background:#64748b;color:white;padding:14px 8px;border-radius:10px;text-decoration:none;font-weight:700;font-size:14px">
      ⏸ Tạm dừng
    </a>
  </div>
  <p style="margin:0;font-size:12px;color:#94a3b8;text-align:center">
    Link hết hạn sau 48 giờ · Chỉ dùng được 1 lần mỗi link
  </p>
  <hr style="border:none;border-top:1px solid #e2e8f0;margin:16px 0">
  <p style="margin:0;font-size:11px;color:#cbd5e1;word-break:break-all">
    Proceed: {proceed_url}<br>Remake: {remake_url}<br>Hold: {hold_url}
  </p>
</div>
</body></html>"""


# ── Public API ─────────────────────────────────────────────────────────────────

async def send_approval_request(
    project_id: str,
    project_title: str,
    step: str,
    extra_info: str = "",
) -> str:
    """
    Create approval token + send email via Resend.
    Always logs URLs to console (useful when Resend not configured).
    Returns the token.
    """
    token = await create_approval_token(project_id, step)
    approve_url = _approval_url(token, "approve")
    reject_url  = _approval_url(token, "reject")
    step_label  = _STEP_LABELS.get(step, step)

    logger.info("-" * 60)
    logger.info("APPROVAL REQUEST: %s | project=%s", step, project_id)
    logger.info("APPROVE: %s", approve_url)
    logger.info("REJECT:  %s", reject_url)
    logger.info("-" * 60)

    subject   = f"[AI Content Factory] {step_label} — {project_title}"
    html_body = _build_email_html(step_label, project_title, extra_info, approve_url, reject_url)
    to        = settings.notification_email

    sent = await send_email_resend(to, subject, html_body)
    if not sent:
        logger.warning("Resend not configured — approval URLs logged above. Set RESEND_API_KEY in Railway.")

    await _send_telegram(
        f"🎬 <b>{step_label}</b>\nDự án: <b>{project_title}</b>\n{extra_info + chr(10) if extra_info else ''}Chọn hành động:",
        [{"text": "✅ Duyệt", "url": approve_url}, {"text": "❌ Từ chối", "url": reject_url}],
    )

    return token


async def send_video_review_request(
    project_id: str,
    project_title: str,
    ai_score: int,
    overall_score: int,
) -> None:
    """Send 3-action video review email: Proceed / Remake / Hold."""
    proceed_token = await create_approval_token(project_id, "video_review")
    remake_token  = await create_approval_token(project_id, "video_review")
    hold_token    = await create_approval_token(project_id, "video_review")

    proceed_url = _approval_url(proceed_token, "proceed")
    remake_url  = _approval_url(remake_token,  "remake")
    hold_url    = _approval_url(hold_token,    "hold")

    logger.info("-" * 60)
    logger.info("VIDEO REVIEW: project=%s score=%d/100", project_id, overall_score)
    logger.info("PROCEED: %s", proceed_url)
    logger.info("REMAKE:  %s", remake_url)
    logger.info("HOLD:    %s", hold_url)
    logger.info("-" * 60)

    subject   = f"[AI Content Factory] Duyệt Video Final — {project_title} ({overall_score}/100)"
    html_body = _build_video_review_html(project_title, ai_score, overall_score, proceed_url, remake_url, hold_url)
    to        = settings.notification_email

    sent = await send_email_resend(to, subject, html_body)
    if not sent:
        logger.warning("Resend not configured — video review URLs logged above.")

    await _send_telegram(
        f"🎬 <b>Duyệt Video Final</b>\nDự án: <b>{project_title}</b>\nĐiểm: {overall_score}/100",
        [
            {"text": "✅ Tiếp tục", "url": proceed_url},
            {"text": "🔄 Làm lại",  "url": remake_url},
            {"text": "⏸ Tạm dừng", "url": hold_url},
        ],
    )


async def send_simple_notification(subject: str, body: str) -> None:
    """Send a plain notification email (no approval buttons)."""
    to = settings.notification_email
    html = f"""<div style="font-family:sans-serif;max-width:560px;margin:auto;padding:24px">
<h2>🎬 AI Content Factory</h2><p>{body}</p></div>"""
    await send_email_resend(to, subject, html)
