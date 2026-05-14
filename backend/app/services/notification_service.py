"""Notification service — Gmail SMTP (primary) + service account fallback.

Approval flow:
  1. send_approval_request() → creates Redis token (48h) → sends email
  2. User clicks Duyệt/Từ chối link in email → POST /approvals/{token}?action=approve|reject
  3. Token resolved → LangGraph resumed

Gmail strategy (personal Gmail):
  • Primary:  Gmail SMTP via App Password (smtp.gmail.com:587)
  • Fallback: Google Workspace service account + DWD (not for @gmail.com)
  • Always:   Log approval URLs to console so dev can test without email config
"""
from __future__ import annotations
import asyncio
import json
import logging
import smtplib
import ssl
import uuid
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import httpx

from ..config import get_settings
from ..redis_client import get_redis

logger = logging.getLogger(__name__)
settings = get_settings()

_TOKEN_TTL = 48 * 3600   # 48 hours

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


# ── Gmail SMTP (personal Gmail + App Password) ────────────────────────────────

async def _send_smtp(to: str, subject: str, html_body: str) -> bool:
    """
    Send via Gmail SMTP using App Password.
    Requires GMAIL_APP_PASSWORD set in .env.
    Returns True on success.
    """
    if not settings.gmail_app_password:
        return False

    sender = settings.gmail_sender_email or settings.notification_email
    # App Passwords are shown in groups of 4 (e.g. "xxxx xxxx xxxx xxxx")
    # Strip spaces — SMTP requires the raw 16-char password
    app_password = settings.gmail_app_password.replace(" ", "")
    loop = asyncio.get_event_loop()

    def _do_send():
        ctx = ssl.create_default_context()
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"AI Content Factory <{sender}>"
        msg["To"]      = to
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ctx)
            smtp.login(sender, app_password)
            smtp.sendmail(sender, to, msg.as_string())

    try:
        await loop.run_in_executor(None, _do_send)
        logger.info("Gmail SMTP sent to %s (subject len=%d)", to, len(subject))
        return True
    except smtplib.SMTPAuthenticationError:
        logger.error(
            "Gmail SMTP auth failed. "
            "Ensure 2-Step Verification is ON and GMAIL_APP_PASSWORD is correct. "
            "Create one at: https://myaccount.google.com/apppasswords"
        )
        return False
    except Exception as e:
        logger.error("Gmail SMTP error: %s", e)
        return False


# ── Gmail API via service account (Google Workspace + DWD only) ───────────────

async def _send_service_account(to: str, subject: str, html_body: str) -> bool:
    """
    Send via Gmail API with service account.
    Only works when Domain-Wide Delegation is configured on a Google Workspace domain.
    Will NOT work for personal @gmail.com accounts.
    """
    sa_path_or_json = settings.gmail_service_account_json
    if not sa_path_or_json:
        return False

    # Resolve: either a file path or raw JSON string
    sa_info: dict | None = None
    path = Path(sa_path_or_json)
    if path.exists():
        sa_info = json.loads(path.read_text())
    else:
        try:
            sa_info = json.loads(sa_path_or_json)
        except (json.JSONDecodeError, ValueError):
            logger.warning("gmail_service_account_json is not a valid path or JSON")
            return False

    try:
        import base64
        from email.mime.text import MIMEText as _MIMEText
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        sender = settings.notification_email
        creds = service_account.Credentials.from_service_account_info(
            sa_info,
            scopes=["https://www.googleapis.com/auth/gmail.send"],
        ).with_subject(sender)   # requires DWD

        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        msg = _MIMEText(html_body, "html", "utf-8")
        msg["To"] = to
        msg["Subject"] = subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: service.users().messages().send(userId="me", body={"raw": raw}).execute(),
        )
        logger.info("Gmail service account sent to %s", to)
        return True
    except Exception as e:
        logger.warning("Gmail service account send failed (likely no DWD): %s", e)
        return False


# ── Telegram ──────────────────────────────────────────────────────────────────

async def _send_telegram(text: str, approve_url: str, reject_url: str) -> None:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": {"inline_keyboard": [[
            {"text": "✅ Duyệt", "url": approve_url},
            {"text": "❌ Từ chối", "url": reject_url},
        ]]},
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json=payload,
            )
        if resp.status_code != 200:
            logger.error("Telegram error %s: %s", resp.status_code, resp.text[:200])
    except Exception as e:
        logger.error("Telegram error: %s", e)


# ── Email body builders ────────────────────────────────────────────────────────

_STEP_LABELS = {
    "script_review":    "Duyệt Kịch Bản",
    "character_review": "Duyệt Nhân Vật",
    "scene_review":     "Duyệt Phân Cảnh",
    "quality_review":   "Duyệt Chất Lượng Video",
    "video_review":     "Duyệt Video Final",
    "seo_review":       "Duyệt Gói SEO",
}


def _build_email_html(step_label: str, project_title: str, extra_info: str, approve_url: str, reject_url: str) -> str:
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


# ── Public API ─────────────────────────────────────────────────────────────────

async def send_approval_request(
    project_id: str,
    project_title: str,
    step: str,
    extra_info: str = "",
) -> str:
    """
    Create approval token + send Gmail notification.
    Always logs the URLs to console (useful when email not configured).
    Returns the token.
    """
    token = await create_approval_token(project_id, step)
    approve_url = _approval_url(token, "approve")
    reject_url  = _approval_url(token, "reject")
    step_label  = _STEP_LABELS.get(step, step)

    # Always log — dev can copy-paste to test without email setup
    logger.info("-" * 60)
    logger.info("APPROVAL REQUEST: %s", step)
    logger.info("APPROVE: %s", approve_url)
    logger.info("REJECT:  %s", reject_url)
    logger.info("-" * 60)

    subject   = f"[AI Content Factory] {step_label} — {project_title}"
    html_body = _build_email_html(step_label, project_title, extra_info, approve_url, reject_url)
    to        = settings.notification_email

    # Try Resend first (if configured), then Gmail SMTP, then service account
    from .resend_service import send_email_resend
    sent = await send_email_resend(to, subject, html_body)
    if not sent:
        sent = await _send_smtp(to, subject, html_body)
    if not sent:
        sent = await _send_service_account(to, subject, html_body)
    if not sent:
        logger.warning(
            "Email not sent (no credentials configured). "
            "To enable: set GMAIL_APP_PASSWORD in .env. "
            "Approval URLs are logged above."
        )

    # Telegram (optional — skip if not configured)
    tg_text = (
        f"🎬 <b>{step_label}</b>\n"
        f"Dự án: <b>{project_title}</b>\n"
        + (f"{extra_info}\n" if extra_info else "")
        + "Chọn hành động:"
    )
    await _send_telegram(tg_text, approve_url, reject_url)

    return token


def _build_video_review_html(
    project_title: str,
    ai_score: int,
    overall_score: int,
    proceed_url: str,
    remake_url: str,
    hold_url: str,
) -> str:
    score_color = "#16a34a" if overall_score >= 75 else "#d97706"
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
    <div style="font-size:13px;margin-top:4px;color:{'#16a34a' if overall_score >= 75 else '#d97706'}">
      {'✓ Đạt ngưỡng chất lượng (≥75)' if overall_score >= 75 else '⚠ Chưa đạt ngưỡng (<75)'}
    </div>
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
    remake_url  = _approval_url(remake_token, "remake")
    hold_url    = _approval_url(hold_token, "hold")

    logger.info("-" * 60)
    logger.info("VIDEO REVIEW REQUEST for project %s", project_id)
    logger.info("PROCEED: %s", proceed_url)
    logger.info("REMAKE:  %s", remake_url)
    logger.info("HOLD:    %s", hold_url)
    logger.info("-" * 60)

    subject   = f"[AI Content Factory] Duyệt Video Final — {project_title} ({overall_score}/100)"
    html_body = _build_video_review_html(project_title, ai_score, overall_score, proceed_url, remake_url, hold_url)
    to        = settings.notification_email

    from .resend_service import send_email_resend
    sent = await send_email_resend(to, subject, html_body)
    if not sent:
        sent = await _send_smtp(to, subject, html_body)
    if not sent:
        await _send_service_account(to, subject, html_body)


async def send_simple_notification(subject: str, body: str) -> None:
    """Send a plain notification email (no approval buttons)."""
    to = settings.notification_email
    html = f"""<div style="font-family:sans-serif;max-width:560px;margin:auto;padding:24px">
<h2>🎬 AI Content Factory</h2><p>{body}</p></div>"""
    sent = await _send_smtp(to, subject, html)
    if not sent:
        await _send_service_account(to, subject, html)
