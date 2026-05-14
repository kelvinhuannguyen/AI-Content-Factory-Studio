"""Resend email service — replaces Gmail SMTP for transactional emails."""
import logging
import httpx
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_RESEND_API_URL = "https://api.resend.com/emails"


async def send_email_resend(to: str, subject: str, html_body: str) -> bool:
    """Send email via Resend API. Returns True on success."""
    if not settings.resend_api_key:
        logger.warning("RESEND_API_KEY not set — skipping Resend send")
        return False

    payload = {
        "from": settings.resend_from_email,
        "to": [to],
        "subject": subject,
        "html": html_body,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                _RESEND_API_URL,
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                json=payload,
            )
        if resp.status_code in (200, 201):
            logger.info("Resend email sent to %s: %s", to, subject)
            return True
        logger.warning("Resend error %d: %s", resp.status_code, resp.text[:200])
        return False
    except Exception as e:
        logger.warning("Resend send failed: %s", e)
        return False
