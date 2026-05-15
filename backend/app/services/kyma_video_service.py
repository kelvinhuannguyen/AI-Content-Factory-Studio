"""KymaAPI video generation — multi-model fallback chain.

Primary:  hailuo-02-768p  (cheap, fast)
Fallback: kling-v2-5-standard (reliable, was working before)
"""
import asyncio
import logging
import httpx
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_VIDEOS_URL    = f"{settings.kymaapi_base_url}/videos/generations"
_JOBS_URL      = f"{settings.kymaapi_base_url}/jobs"
_POLL_INTERVAL = 10    # seconds between polls
_MAX_WAIT      = 600   # 10 min ceiling


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
    Submit video job to KymaAPI — tries primary model then fallback.
    Returns MP4 bytes.
    """
    primary   = model or settings.kymaapi_video_model
    fallback  = settings.kymaapi_video_model_fallback

    models_to_try = [primary]
    if fallback and fallback != primary:
        models_to_try.append(fallback)

    last_err: Exception | None = None
    for m in models_to_try:
        try:
            result = await _submit_and_poll(m, prompt, duration_seconds, aspect_ratio)
            return result
        except VideoGenError as e:
            logger.warning("KymaAPI model=%s failed: %s — trying next", m, e)
            last_err = e

    raise VideoGenError(f"All KymaAPI video models failed. Last error: {last_err}")


async def _submit_and_poll(
    model: str,
    prompt: str,
    duration_seconds: int,
    aspect_ratio: str,
) -> bytes:
    # Kling supports 5 or 10s; Hailuo accepts duration directly
    api_duration = 5 if duration_seconds <= 7 else 10

    payload: dict = {
        "model": model,
        "prompt": prompt,
        "duration": api_duration,
        "aspect_ratio": aspect_ratio,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(_VIDEOS_URL, headers=_headers(), json=payload)

    if resp.status_code not in (200, 202):
        raise VideoGenError(f"KymaAPI submit {resp.status_code} (model={model}): {resp.text[:300]}")

    data = resp.json()

    # Sync response (rare)
    if "data" in data and data["data"]:
        url = data["data"][0].get("url")
        if url:
            return await _download(url)

    job_id = data.get("id") or data.get("job_id")
    if not job_id:
        raise VideoGenError(f"No job_id in response (model={model}): {data}")

    logger.info("KymaAPI video job submitted: %s (model=%s, %ds, %s)", job_id, model, api_duration, aspect_ratio)
    return await _poll_and_download(job_id, model)


async def _poll_and_download(job_id: str, model: str) -> bytes:
    waited = 0
    async with httpx.AsyncClient(timeout=15) as client:
        while waited < _MAX_WAIT:
            resp = await client.get(f"{_JOBS_URL}/{job_id}", headers=_headers())
            if resp.status_code == 200:
                job = resp.json()
                status = job.get("status", "")
                logger.debug("Video job %s status: %s (%ds)", job_id, status, waited)
                if status == "succeeded":
                    output = job.get("output", {})
                    url = (
                        output.get("url")
                        or (output.get("videos") or [{}])[0].get("url")
                        or (output.get("data") or [{}])[0].get("url")
                    )
                    if url:
                        return await _download(url)
                    raise VideoGenError(f"Job {job_id} succeeded but no URL in output")
                if status in ("failed", "cancelled"):
                    err_detail = job.get("error", "")
                    raise VideoGenError(f"Video job {job_id} {status} (model={model}): {err_detail}")
            await asyncio.sleep(_POLL_INTERVAL)
            waited += _POLL_INTERVAL

    raise VideoGenError(f"Video job {job_id} timed out after {_MAX_WAIT}s (model={model})")


async def _download(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
        resp = await client.get(url)
    if resp.status_code != 200:
        raise VideoGenError(f"Download failed {resp.status_code}: {url}")
    return resp.content
