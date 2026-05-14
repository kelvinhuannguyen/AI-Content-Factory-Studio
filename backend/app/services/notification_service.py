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
# Table-based layout — compatible with Outlook 2007-2021, Gmail, Apple Mail, Yahoo.
# Buttons use MSO VML (Outlook) + standard <a> fallback for modern clients.

_STEP_LABELS = {
    "script_review":    "Duyệt Kịch Bản",
    "character_review": "Duyệt Nhân Vật",
    "scene_review":     "Duyệt Phân Cảnh",
    "quality_review":   "Duyệt Chất Lượng Video",
    "video_review":     "Duyệt Video Final",
    "seo_review":       "Duyệt Gói SEO",
}

_FONT = "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
_BG   = "#f4f4f5"
_CARD = "#ffffff"
_TEXT = "#18181b"
_MUTED = "#71717a"
_BORDER = "#e4e4e7"
_BRAND = "#6d28d9"   # violet-700


def _vml_btn(url: str, label: str, bg: str, width: int = 240) -> str:
    """MSO VML rounded button — renders correctly in Outlook 2007-2021."""
    return (
        f'<!--[if mso]><v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" '
        f'href="{url}" style="height:44px;width:{width}px;v-text-anchor:middle;" '
        f'arcsize="12%" stroke="f" fillcolor="{bg}">'
        f'<w:anchorlock/><center style="{_FONT};color:#ffffff;font-size:14px;'
        f'font-weight:700;">{label}</center></v:roundrect><![endif]-->'
        f'<!--[if !mso]><!-->'
        f'<a href="{url}" style="display:inline-block;background:{bg};color:#ffffff;'
        f'{_FONT};font-size:14px;font-weight:700;text-decoration:none;'
        f'padding:12px 28px;border-radius:6px;mso-hide:all;">{label}</a>'
        f'<!--<![endif]-->'
    )


def _base_template(
    preheader: str,
    headline: str,
    subhead: str,
    body_rows: str,
    footer_lines: str,
) -> str:
    return f"""<!DOCTYPE html>
<html lang="vi" xmlns:v="urn:schemas-microsoft-com:vml">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<meta name="x-apple-disable-message-reformatting">
<!--[if mso]><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml><![endif]-->
<title>{headline}</title>
</head>
<body style="margin:0;padding:0;background:{_BG};{_FONT};">
<!--[if mso | IE]><table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background:{_BG};"><tr><td><![endif]-->

<!-- Preheader (hidden preview text) -->
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;
  color:{_BG};font-size:1px;line-height:1px;">{preheader}&nbsp;&#847;&nbsp;&#847;&nbsp;&#847;</div>

<!-- Outer wrapper -->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
  style="background:{_BG};margin:0;padding:0;">
  <tr>
    <td align="center" style="padding:40px 16px;">

      <!-- Card -->
      <table role="presentation" width="560" cellpadding="0" cellspacing="0" border="0"
        style="background:{_CARD};border-radius:8px;border:1px solid {_BORDER};
               width:100%;max-width:560px;">

        <!-- Brand header bar -->
        <tr>
          <td style="background:{_BRAND};border-radius:8px 8px 0 0;padding:20px 32px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td>
                  <span style="color:#ffffff;{_FONT};font-size:16px;font-weight:700;
                    letter-spacing:-0.01em;">AI Content Factory</span>
                </td>
                <td align="right">
                  <span style="color:rgba(255,255,255,0.7);{_FONT};font-size:12px;">Studio</span>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="padding:32px;">

            <!-- Headline -->
            <h1 style="margin:0 0 4px;{_FONT};font-size:22px;font-weight:700;
              color:{_TEXT};letter-spacing:-0.02em;">{headline}</h1>
            <p style="margin:0 0 28px;{_FONT};font-size:14px;color:{_MUTED};">{subhead}</p>

            <!-- Dynamic body rows -->
            {body_rows}

          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="padding:16px 32px 28px;border-top:1px solid {_BORDER};">
            <p style="margin:0;{_FONT};font-size:12px;color:{_MUTED};line-height:1.6;">
              {footer_lines}
            </p>
          </td>
        </tr>

      </table>
      <!-- /Card -->

    </td>
  </tr>
</table>

<!--[if mso | IE]></td></tr></table><![endif]-->
</body>
</html>"""


def _info_row(label: str, value: str, extra: str = "") -> str:
    extra_html = f'<p style="margin:6px 0 0;{_FONT};font-size:13px;color:{_MUTED};">{extra}</p>' if extra else ""
    return f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
  style="background:#fafafa;border:1px solid {_BORDER};border-radius:6px;
         margin-bottom:24px;">
  <tr>
    <td style="padding:14px 16px;">
      <p style="margin:0 0 2px;{_FONT};font-size:11px;font-weight:600;color:{_MUTED};
        text-transform:uppercase;letter-spacing:0.06em;">Dự án</p>
      <p style="margin:0;{_FONT};font-size:16px;font-weight:700;color:{_TEXT};">{value}</p>
      {extra_html}
    </td>
  </tr>
</table>"""


def _script_preview_block(script_content: str) -> str:
    if not script_content.strip():
        return ""
    # Cap at ~2000 chars to keep email readable
    preview = script_content[:2000]
    if len(script_content) > 2000:
        preview += "\n\n[... xem toàn bộ kịch bản trên dashboard ...]"
    # Escape HTML special chars
    preview = preview.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    preview = preview.replace("\n", "<br>")
    return f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
  style="border:1px solid {_BORDER};border-radius:6px;margin-bottom:24px;">
  <tr>
    <td style="padding:6px 16px;background:#f4f4f5;border-radius:6px 6px 0 0;
      border-bottom:1px solid {_BORDER};">
      <p style="margin:0;{_FONT};font-size:11px;font-weight:600;color:{_MUTED};
        text-transform:uppercase;letter-spacing:0.06em;">Nội dung kịch bản</p>
    </td>
  </tr>
  <tr>
    <td style="padding:16px;max-height:400px;overflow:hidden;">
      <p style="margin:0;{_FONT};font-size:13px;color:{_TEXT};line-height:1.7;
        white-space:pre-wrap;">{preview}</p>
    </td>
  </tr>
</table>"""


def _build_email_html(
    step_label: str, project_title: str, extra_info: str,
    approve_url: str, reject_url: str,
    script_content: str = "",
) -> str:
    info = _info_row("Dự án", project_title, extra_info)
    script_block = _script_preview_block(script_content)
    buttons = f"""
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%"
  style="margin-bottom:28px;">
  <tr>
    <td width="48%" align="center">
      {_vml_btn(approve_url, "Duyệt", "#16a34a", 220)}
    </td>
    <td width="4%"></td>
    <td width="48%" align="center">
      {_vml_btn(reject_url, "Từ chối", "#dc2626", 220)}
    </td>
  </tr>
</table>"""
    footer = (
        f'Link hết hạn sau <strong>48 giờ</strong> &middot; Chỉ dùng được 1 lần.<br>'
        f'Nếu nút không hoạt động, copy URL bên dưới:<br>'
        f'<span style="color:{_BRAND};">Duyệt:</span> '
        f'<a href="{approve_url}" style="color:{_BRAND};word-break:break-all;">{approve_url}</a><br>'
        f'<span style="color:#dc2626;">Từ chối:</span> '
        f'<a href="{reject_url}" style="color:#dc2626;word-break:break-all;">{reject_url}</a>'
    )
    return _base_template(
        preheader=f"Yêu cầu duyệt: {step_label} — {project_title}",
        headline=step_label,
        subhead="Vui lòng xem xét và chọn hành động bên dưới.",
        body_rows=info + script_block + buttons,
        footer_lines=footer,
    )


def _build_video_review_html(
    project_title: str, ai_score: int, overall_score: int,
    proceed_url: str, remake_url: str, hold_url: str,
) -> str:
    score_color = "#16a34a" if overall_score >= 75 else "#d97706"
    status_text = "Dat nguong chat luong (>=75/100)" if overall_score >= 75 else "Chua dat nguong (<75/100)"
    bar_pct = min(100, overall_score)

    info = _info_row("Dự án", project_title)
    score_block = f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
  style="background:#fafafa;border:1px solid {_BORDER};border-radius:6px;
         margin-bottom:8px;">
  <tr>
    <td style="padding:20px 24px;text-align:center;">
      <p style="margin:0 0 4px;{_FONT};font-size:52px;font-weight:900;
        color:{score_color};line-height:1;">{overall_score}</p>
      <p style="margin:0 0 6px;{_FONT};font-size:14px;color:{_MUTED};">
        / 100 &nbsp;&middot;&nbsp; AI Score: {ai_score}/10</p>
      <!-- Score bar -->
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
        style="background:#e4e4e7;border-radius:4px;height:6px;margin:0 auto 8px;">
        <tr>
          <td width="{bar_pct}%" style="background:{score_color};border-radius:4px;height:6px;"></td>
          <td></td>
        </tr>
      </table>
      <p style="margin:0;{_FONT};font-size:13px;color:{score_color};font-weight:600;">
        {status_text}</p>
    </td>
  </tr>
</table>
<p style="margin:0 0 20px;{_FONT};font-size:12px;color:{_MUTED};text-align:center;">
  Chọn hành động phù hợp để tiếp tục luồng sản xuất.</p>"""

    buttons = f"""
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%"
  style="margin-bottom:28px;">
  <tr>
    <td width="32%" align="center" style="padding:0 4px 0 0;">
      {_vml_btn(proceed_url, "Tiep tuc", "#16a34a", 160)}
    </td>
    <td width="32%" align="center" style="padding:0 2px;">
      {_vml_btn(remake_url, "Lam lai", "#d97706", 160)}
    </td>
    <td width="32%" align="center" style="padding:0 0 0 4px;">
      {_vml_btn(hold_url, "Tam dung", "#52525b", 160)}
    </td>
  </tr>
</table>"""

    footer = (
        f'Link hết hạn sau <strong>48 giờ</strong> &middot; Mỗi link chỉ dùng được 1 lần.<br>'
        f'<a href="{proceed_url}" style="color:#16a34a;word-break:break-all;">Tiep tuc</a> &nbsp;|&nbsp; '
        f'<a href="{remake_url}" style="color:#d97706;word-break:break-all;">Lam lai</a> &nbsp;|&nbsp; '
        f'<a href="{hold_url}" style="color:#52525b;word-break:break-all;">Tam dung</a>'
    )
    return _base_template(
        preheader=f"Video dat {overall_score}/100 diem — chon hanh dong",
        headline="Duyet Video Final",
        subhead=f"AI da cham diem video cua ban: {overall_score}/100 diem.",
        body_rows=info + score_block + buttons,
        footer_lines=footer,
    )


# ── Public API ─────────────────────────────────────────────────────────────────

async def send_approval_request(
    project_id: str,
    project_title: str,
    step: str,
    extra_info: str = "",
    script_content: str = "",
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
    html_body = _build_email_html(step_label, project_title, extra_info, approve_url, reject_url, script_content)
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
