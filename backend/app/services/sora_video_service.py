"""OpenAI Sora-2 video generation.

POST https://api.openai.com/v1/videos
Poll GET /videos/{id} until status=completed
Download GET /videos/{id}/content → MP4 bytes
"""
import asyncio
import logging
import httpx
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_BASE   = "https://api.openai.com/v1"
_POLL   = 10    # seconds between polls
_MAX_WAIT = 600  # 10 min ceiling


class SoraError(Exception):
    pass


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }

# aspect_ratio → Sora size string
_SIZE_MAP = {
    "9:16":  "1080x1920",
    "16:9":  "1920x1080",
    "1:1":   "1080x1080",
    "4:3":   "1440x1080",
    "3:4":   "1080x1440",
}


async def generate_video_clip(
    prompt: str,
    duration_seconds: int = 5,
    aspect_ratio: str = "9:16",
    model: str = "sora-2",
) -> bytes:
    """Submit Sora job and poll until completed. Returns MP4 bytes."""
    if not settings.openai_api_key:
        raise SoraError("openai_api_key not configured")

    size = _SIZE_MAP.get(aspect_ratio, "1080x1920")
    # Sora requires seconds as STRING: '4', '8', or '12'
    if duration_seconds <= 4:
        sora_seconds = "4"
    elif duration_seconds <= 8:
        sora_seconds = "8"
    else:
        sora_seconds = "12"

    payload = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "seconds": sora_seconds,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{_BASE}/videos", headers=_headers(), json=payload)

    if resp.status_code not in (200, 202):
        raise SoraError(f"Sora submit {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    video_id = data.get("id")
    if not video_id:
        raise SoraError(f"No video id in Sora response: {data}")

    logger.info("Sora job submitted: %s (model=%s, %ds, %s)", video_id, model, sora_seconds, size)
    return await _poll_and_download(video_id)


async def _poll_and_download(video_id: str) -> bytes:
    poll_url = f"{_BASE}/videos/{video_id}"
    waited = 0

    async with httpx.AsyncClient(timeout=20) as client:
        while waited < _MAX_WAIT:
            await asyncio.sleep(_POLL)
            waited += _POLL

            resp = await client.get(poll_url, headers=_headers())
            if resp.status_code != 200:
                logger.warning("Sora poll %s (waited %ds)", resp.status_code, waited)
                continue

            job = resp.json()
            status = job.get("status", "")
            progress = job.get("progress", 0)
            logger.debug("Sora %s: %s %d%% (%ds)", video_id, status, progress, waited)

            if status == "completed":
                return await _download(video_id)
            if status == "failed":
                raise SoraError(f"Sora job {video_id} failed")

    raise SoraError(f"Sora job {video_id} timed out after {_MAX_WAIT}s")


async def _download(video_id: str) -> bytes:
    """Download MP4 content from completed Sora job."""
    dl_url = f"{_BASE}/videos/{video_id}/content"
    async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
        resp = await client.get(dl_url, headers=_headers())
    if resp.status_code != 200:
        raise SoraError(f"Sora download failed {resp.status_code}: {dl_url}")
    return resp.content
