"""KymaAPI video generation — kling-3-pro async job pattern."""
import asyncio
import logging
import httpx
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_VIDEOS_URL = f"{settings.kymaapi_base_url}/videos/generations"
_JOBS_URL   = f"{settings.kymaapi_base_url}/jobs"
_POLL_INTERVAL = 10   # giây
_MAX_WAIT      = 600  # 10 phút max cho video


class VideoGenError(Exception):
    pass


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.kymaapi_key}",
        "Content-Type": "application/json",
    }


async def generate_video_clip(
    prompt: str,
    duration_seconds: int = 5,
    aspect_ratio: str = "9:16",
    model: str = "",
) -> bytes:
    """
    Submit video generation job to KymaAPI and poll until done.
    Returns MP4 bytes.
    aspect_ratio: "9:16" for short video, "16:9" for long video
    """
    model = model or settings.kymaapi_video_model   # kling-3-pro

    # KymaAPI duration: 5 or 10 seconds for kling
    api_duration = 5 if duration_seconds <= 7 else 10

    payload = {
        "model": model,
        "prompt": prompt,
        "duration": api_duration,
        "aspect_ratio": aspect_ratio,
        "n": 1,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(_VIDEOS_URL, headers=_headers(), json=payload)

    if resp.status_code not in (200, 202):
        raise VideoGenError(f"KymaAPI video submit {resp.status_code}: {resp.text[:300]}")

    data = resp.json()

    # Sync response (rare)
    if "data" in data and data["data"]:
        url = data["data"][0].get("url")
        if url:
            return await _download(url)

    job_id = data.get("id") or data.get("job_id")
    if not job_id:
        raise VideoGenError(f"No job_id in response: {data}")

    logger.info("Video job submitted: %s (model=%s, %ds, %s)", job_id, model, api_duration, aspect_ratio)
    return await _poll_and_download(job_id)


async def _poll_and_download(job_id: str) -> bytes:
    waited = 0
    async with httpx.AsyncClient(timeout=15) as client:
        while waited < _MAX_WAIT:
            resp = await client.get(f"{_JOBS_URL}/{job_id}", headers=_headers())
            if resp.status_code == 200:
                job = resp.json()
                status = job.get("status", "")
                logger.debug("Video job %s status: %s (waited %ds)", job_id, status, waited)
                if status == "succeeded":
                    output = job.get("output", {})
                    url = (
                        output.get("url")
                        or (output.get("videos") or [{}])[0].get("url")
                        or (output.get("data") or [{}])[0].get("url")
                    )
                    if url:
                        return await _download(url)
                    raise VideoGenError("Job succeeded but no video URL in output")
                if status in ("failed", "cancelled"):
                    raise VideoGenError(f"Video job {job_id} {status}: {job.get('error', '')}")
            await asyncio.sleep(_POLL_INTERVAL)
            waited += _POLL_INTERVAL

    raise VideoGenError(f"Video job {job_id} timed out after {_MAX_WAIT}s")


async def _download(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
        resp = await client.get(url)
    if resp.status_code != 200:
        raise VideoGenError(f"Download failed {resp.status_code}: {url}")
    return resp.content
