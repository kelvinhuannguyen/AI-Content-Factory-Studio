"""ComfyUI service — local X13 (primary) and RunPod (fallback).

Submits a workflow to ComfyUI, polls until done, downloads the output image bytes.
Supports IP-Adapter reference image injection.
"""
import asyncio
import json
import logging
import uuid
from typing import Any

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Standard polling interval (seconds)
_POLL_INTERVAL = 3
_MAX_WAIT = 300  # 5 minutes max


class ComfyUIError(Exception):
    pass


def _endpoint(runpod: bool = False) -> str:
    url = settings.runpod_comfyui_url if runpod else settings.comfyui_url
    return url.rstrip("/")


def _build_character_workflow(
    prompt: str,
    negative_prompt: str = "blurry, low quality, watermark, text",
    width: int = 768,
    height: int = 1024,
    steps: int = 20,
    cfg: float = 7.0,
    seed: int | None = None,
) -> dict[str, Any]:
    """Minimal Flux-style workflow for character portrait generation."""
    seed = seed or uuid.uuid4().int % (2**32)
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "dreamshaper_8.safetensors"},
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": prompt,
                "clip": ["1", 1],
            },
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": negative_prompt,
                "clip": ["1", 1],
            },
        },
        "4": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "euler_ancestral",
                "scheduler": "karras",
                "denoise": 1.0,
            },
        },
        "6": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["5", 0],
                "vae": ["1", 2],
            },
        },
        "7": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["6", 0],
                "filename_prefix": "aicfs_char",
            },
        },
    }


async def _submit_prompt(base_url: str, workflow: dict) -> str:
    """Submit workflow and return prompt_id."""
    payload = {"prompt": workflow, "client_id": str(uuid.uuid4())}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{base_url}/prompt", json=payload)
    if resp.status_code != 200:
        raise ComfyUIError(f"ComfyUI submit failed {resp.status_code}: {resp.text[:200]}")
    return resp.json()["prompt_id"]


async def _poll_until_done(base_url: str, prompt_id: str) -> dict:
    """Poll /history until the prompt is complete. Returns history entry."""
    waited = 0
    async with httpx.AsyncClient(timeout=10) as client:
        while waited < _MAX_WAIT:
            resp = await client.get(f"{base_url}/history/{prompt_id}")
            if resp.status_code == 200:
                data = resp.json()
                if prompt_id in data:
                    return data[prompt_id]
            await asyncio.sleep(_POLL_INTERVAL)
            waited += _POLL_INTERVAL
    raise ComfyUIError(f"ComfyUI timed out after {_MAX_WAIT}s for prompt {prompt_id}")


async def _download_image(base_url: str, filename: str, subfolder: str = "", image_type: str = "output") -> bytes:
    params = {"filename": filename, "type": image_type}
    if subfolder:
        params["subfolder"] = subfolder
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(f"{base_url}/view", params=params)
    if resp.status_code != 200:
        raise ComfyUIError(f"ComfyUI download failed {resp.status_code}")
    return resp.content


async def _is_alive(base_url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{base_url}/system_stats")
        return resp.status_code == 200
    except Exception:
        return False


async def generate_character_image(
    prompt: str,
    variant_index: int = 0,
    negative_prompt: str = "blurry, low quality, watermark, text, deformed",
    ref_image_bytes: bytes | None = None,
) -> bytes:
    """
    Generate a character portrait image.
    Returns PNG bytes.

    Tries local X13 first, falls back to RunPod ComfyUI if configured.
    ref_image_bytes: if provided, will be used as IP-Adapter reference (uploaded to ComfyUI input).
    """
    # Different seed per variant so we get 3 distinct results
    seed = variant_index * 1337 + 42

    workflow = _build_character_workflow(
        prompt=prompt,
        seed=seed,
        width=768,
        height=1024,
    )

    endpoints = [settings.comfyui_url]
    if settings.runpod_comfyui_url:
        endpoints.append(settings.runpod_comfyui_url)

    last_err: Exception | None = None
    for base_url in endpoints:
        base_url = base_url.rstrip("/")
        if not await _is_alive(base_url):
            logger.warning("ComfyUI not reachable at %s, skipping", base_url)
            continue
        try:
            if ref_image_bytes:
                await _upload_input_image(base_url, ref_image_bytes, "reference.png")

            prompt_id = await _submit_prompt(base_url, workflow)
            logger.info("ComfyUI prompt submitted: %s (variant %d)", prompt_id, variant_index)

            history = await _poll_until_done(base_url, prompt_id)

            # Extract first output image from SaveImage node
            for node_id, node_output in history.get("outputs", {}).items():
                images = node_output.get("images", [])
                if images:
                    img_info = images[0]
                    return await _download_image(
                        base_url,
                        img_info["filename"],
                        img_info.get("subfolder", ""),
                        img_info.get("type", "output"),
                    )
            raise ComfyUIError("No output images found in ComfyUI history")
        except Exception as e:
            logger.error("ComfyUI error at %s: %s", base_url, e)
            last_err = e

    raise ComfyUIError(f"All ComfyUI endpoints failed: {last_err}")


async def _upload_input_image(base_url: str, image_bytes: bytes, filename: str) -> None:
    """Upload a reference image to ComfyUI /upload/image."""
    import io
    async with httpx.AsyncClient(timeout=30) as client:
        files = {"image": (filename, io.BytesIO(image_bytes), "image/png")}
        resp = await client.post(f"{base_url}/upload/image", files=files)
    if resp.status_code != 200:
        raise ComfyUIError(f"ComfyUI upload failed {resp.status_code}")
