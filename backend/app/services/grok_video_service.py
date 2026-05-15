"""xAI Grok video generation — async job pattern.

Endpoint:  POST https://api.x.ai/v1/videos/generations
Poll:      GET  https://api.x.ai/v1/videos/generations/{request_id}
Status:    pending → done | failed | expired
"""
import asyncio
import logging
import httpx
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_BASE      = "https://api.x.ai/v1"
_GEN_URL   = f"{_BASE}/videos/generations"
_POLL_SEC  = 15
_MAX_WAIT  = 600   # 10 minutes


class VideoGenError(Exception):
    pass


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.xai_api_key}",
        "Content-Type": "application/json",
    }


_VALID_RATIOS = {"16:9", "9:16", "1:1", "4:3", "3:4", "3:2", "2:3"}


async def generate_video_clip(
    prompt: str,
    duration_seconds: int = 5,
    aspect_ratio: str = "9:16",
    model: str = "",
) -> bytes:
    """
    Submit a Grok video job and poll until done. Returns MP4 bytes.
    Grok supports exact durations 1–15s and proper aspect_ratio param.
    """
    model = model or settings.xai_video_model

    duration = max(1, min(15, int(duration_seconds)))
    if aspect_ratio not in _VALID_RATIOS:
        aspect_ratio = "9:16"

    payload = {
        "model": model,
        "prompt": prompt,
        "duration": duration,
        "aspect_ratio": aspect_ratio,
        "resolution": "720p",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(_GEN_URL, headers=_headers(), json=payload)

    if resp.status_code not in (200, 202):
        raise VideoGenError(f"xAI submit {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    request_id = data.get("request_id")
    if not request_id:
        raise VideoGenError(f"No request_id in response: {data}")

    logger.info("Grok video submitted: %s (model=%s, %ds, %s)", request_id, model, duration, aspect_ratio)
    return await _poll_and_download(request_id)


async def _poll_and_download(request_id: str) -> bytes:
    poll_url = f"{_GEN_URL}/{request_id}"
    waited = 0
    async with httpx.AsyncClient(timeout=15) as client:
        while waited < _MAX_WAIT:
            resp = await client.get(poll_url, headers=_headers())
            if resp.status_code == 200:
                job = resp.json()
                status = job.get("status", "")
                logger.debug("Grok video %s: %s (%ds waited)", request_id, status, waited)
                if status == "done":
                    url = job.get("video_url")
                    if url:
                        return await _download(url)
                    raise VideoGenError("Job done but no video_url in response")
                if status in ("failed", "expired"):
                    raise VideoGenError(f"Grok video {request_id} {status}")
            await asyncio.sleep(_POLL_SEC)
            waited += _POLL_SEC

    raise VideoGenError(f"Grok video {request_id} timed out after {_MAX_WAIT}s")


async def _download(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
        resp = await client.get(url)
    if resp.status_code != 200:
        raise VideoGenError(f"Download failed {resp.status_code}: {url}")
    return resp.content
