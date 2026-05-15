"""Google Veo 3.1 video generation — fallback for KymaAPI Hailuo.

Flow:
  POST .../models/{model}:predictLongRunning  → {"name": "operations/xxx"}
  GET  .../operations/xxx  (poll every 10s)   → {"done": true, "response": {...}}
  Extract: response.generateVideoResponse.generatedSamples[0].video.uri
"""
import asyncio
import logging
import httpx
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_BASE = "https://generativelanguage.googleapis.com/v1beta"
_POLL_SEC = 10
_MAX_WAIT = 400   # docs say max ~6 min; 400s = safe ceiling


class VeoVideoError(Exception):
    pass


def _headers() -> dict:
    return {
        "x-goog-api-key": settings.gemini_api_key,
        "Content-Type": "application/json",
    }


async def generate_video_clip(
    prompt: str,
    duration_seconds: int = 5,
    aspect_ratio: str = "9:16",
    model: str = "",
) -> bytes:
    """Submit Veo job and poll until done. Returns MP4 bytes."""
    if not settings.gemini_api_key:
        raise VeoVideoError("gemini_api_key not configured — set GEMINI_API_KEY in Railway")

    resolved_model = model or settings.veo_video_model
    submit_url = f"{_BASE}/models/{resolved_model}:predictLongRunning"

    payload = {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "aspectRatio": aspect_ratio,   # "9:16" | "16:9" | "1:1"
            "resolution": "720p",
        },
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(submit_url, headers=_headers(), json=payload)

    if resp.status_code not in (200, 202):
        raise VeoVideoError(f"Veo submit {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    operation_name = data.get("name")
    if not operation_name:
        raise VeoVideoError(f"No operation name in Veo response: {data}")

    logger.info("Veo video submitted: %s (model=%s)", operation_name, resolved_model)
    return await _poll_and_download(operation_name)


async def _poll_and_download(operation_name: str) -> bytes:
    poll_url = f"{_BASE}/{operation_name}"
    waited = 0

    async with httpx.AsyncClient(timeout=20) as client:
        while waited < _MAX_WAIT:
            await asyncio.sleep(_POLL_SEC)
            waited += _POLL_SEC

            resp = await client.get(poll_url, headers=_headers())
            if resp.status_code != 200:
                logger.warning("Veo poll %s (waited %ds)", resp.status_code, waited)
                continue

            job = resp.json()
            if not job.get("done"):
                logger.debug("Veo pending (waited %ds)", waited)
                continue

            if "error" in job:
                raise VeoVideoError(f"Veo operation failed: {job['error']}")

            try:
                uri = job["response"]["generateVideoResponse"]["generatedSamples"][0]["video"]["uri"]
            except (KeyError, IndexError) as e:
                raise VeoVideoError(f"Unexpected Veo response: {e} — {str(job)[:300]}")

            logger.info("Veo video ready: %s", uri)
            return await _download(uri)

    raise VeoVideoError(f"Veo operation timed out after {_MAX_WAIT}s")


async def _download(uri: str) -> bytes:
    # URI may require API key header for authenticated download
    async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
        resp = await client.get(uri, headers=_headers())
    if resp.status_code != 200:
        raise VeoVideoError(f"Download failed {resp.status_code}: {uri}")
    return resp.content
