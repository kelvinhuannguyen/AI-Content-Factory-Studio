"""Image generation fallback chain.

Chain order:
  1. ComfyUI (local X13 or RunPod)
  2. KymaAPI → flux-1.1-ultra (async job)
  3. Skip further providers (ChatFPT / Banana not yet configured)

Returns: PNG bytes
"""
import asyncio
import logging

import httpx

from ..config import get_settings
from .comfyui_service import generate_character_image as comfyui_generate, ComfyUIError

logger = logging.getLogger(__name__)
settings = get_settings()

_KYMA_IMAGES_URL = f"{settings.kymaapi_base_url}/images/generations"
_KYMA_JOBS_URL = f"{settings.kymaapi_base_url}/jobs"
_POLL_INTERVAL = 5
_MAX_WAIT = 300


class ImageGenError(Exception):
    pass


async def _kymaapi_generate(prompt: str) -> bytes:
    """Submit a flux-1.1-ultra job to KymaAPI and poll until done."""
    headers = {
        "Authorization": f"Bearer {settings.kymaapi_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.kymaapi_image_model,  # flux-1.1-ultra
        "prompt": prompt,
        "n": 1,
        "size": "768x1024",
        "response_format": "url",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(_KYMA_IMAGES_URL, headers=headers, json=payload)

    if resp.status_code not in (200, 202):
        raise ImageGenError(f"KymaAPI submit failed {resp.status_code}: {resp.text[:200]}")

    data = resp.json()

    # Sync response (some models return immediately)
    if "data" in data and data["data"]:
        image_url = data["data"][0].get("url")
        if image_url:
            return await _download_url(image_url)

    # Async job
    job_id = data.get("id") or data.get("job_id")
    if not job_id:
        raise ImageGenError(f"KymaAPI: no job_id in response: {data}")

    return await _poll_job(job_id, headers)


async def _poll_job(job_id: str, headers: dict) -> bytes:
    waited = 0
    async with httpx.AsyncClient(timeout=15) as client:
        while waited < _MAX_WAIT:
            resp = await client.get(f"{_KYMA_JOBS_URL}/{job_id}", headers=headers)
            if resp.status_code == 200:
                job = resp.json()
                status = job.get("status", "")
                if status == "succeeded":
                    output = job.get("output", {})
                    url = (
                        output.get("url")
                        or (output.get("images") or [{}])[0].get("url")
                    )
                    if url:
                        return await _download_url(url)
                    raise ImageGenError("KymaAPI job succeeded but no URL in output")
                if status in ("failed", "cancelled"):
                    raise ImageGenError(f"KymaAPI job {job_id} {status}")
            await asyncio.sleep(_POLL_INTERVAL)
            waited += _POLL_INTERVAL
    raise ImageGenError(f"KymaAPI job {job_id} timed out after {_MAX_WAIT}s")


async def _download_url(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        resp = await client.get(url)
    if resp.status_code != 200:
        raise ImageGenError(f"Failed to download image from {url}: {resp.status_code}")
    return resp.content


async def generate_image(
    prompt: str,
    variant_index: int = 0,
    ref_image_bytes: bytes | None = None,
) -> tuple[bytes, str]:
    """
    Generate an image using the fallback chain.
    Returns (image_bytes, provider_used).
    """
    # 1. Try ComfyUI
    try:
        img = await comfyui_generate(prompt, variant_index=variant_index, ref_image_bytes=ref_image_bytes)
        return img, "comfyui"
    except ComfyUIError as e:
        logger.warning("ComfyUI failed (variant %d): %s — falling back to KymaAPI", variant_index, e)

    # 2. Try KymaAPI
    if settings.kymaapi_key:
        try:
            img = await _kymaapi_generate(prompt)
            return img, "kymaapi"
        except ImageGenError as e:
            logger.warning("KymaAPI failed: %s", e)

    raise ImageGenError("All image generation providers failed for variant %d" % variant_index)
