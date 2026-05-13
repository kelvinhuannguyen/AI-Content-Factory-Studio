"""KymaAPI LLM wrapper — text completion + vision (GPT-5.4 / GPT-5.5 fallback)."""
import base64
import json
import logging
from typing import Any
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

KYMA_CHAT_URL = f"{settings.kymaapi_base_url}/chat/completions"


class LLMError(Exception):
    pass


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
    reraise=True,
)
async def chat_completion(
    system_prompt: str,
    user_prompt: str,
    model: str = "",          # defaults to config value
    temperature: float = 0.7,
    max_tokens: int = 4096,
    response_format: str = "json_object",  # "json_object" | "text"
) -> str:
    """Call KymaAPI (OpenAI-compatible) and return raw string response."""
    resolved_model = model or settings.kymaapi_llm_model
    headers = {
        "Authorization": f"Bearer {settings.kymaapi_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": resolved_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format == "json_object":
        payload["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(KYMA_CHAT_URL, headers=headers, json=payload)

    if resp.status_code != 200:
        logger.error("KymaAPI error %s: %s", resp.status_code, resp.text[:500])
        raise LLMError(f"KymaAPI returned {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    return data["choices"][0]["message"]["content"]


async def chat_json(
    system_prompt: str,
    user_prompt: str,
    **kwargs,
) -> Any:
    """Call chat_completion and parse JSON response."""
    raw = await chat_completion(
        system_prompt, user_prompt, response_format="json_object", **kwargs
    )
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error("JSON parse error from LLM: %s\nRaw: %s", e, raw[:500])
        raise LLMError(f"LLM returned invalid JSON: {e}") from e


async def chat_vision(
    system_prompt: str,
    user_prompt: str,
    images: list[bytes],
    image_media_type: str = "image/jpeg",
    temperature: float = 0.3,
    max_tokens: int = 2048,
) -> Any:
    """
    Call KymaAPI vision endpoint with base64-encoded images.
    Tries gpt-5.4 first; falls back to gpt-5.5 if unavailable.
    Returns parsed JSON dict.
    """
    models = [settings.kymaapi_vision_model, settings.kymaapi_vision_model_fallback]
    last_err: Exception | None = None

    for model in models:
        try:
            result = await _chat_vision_request(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                images=images,
                image_media_type=image_media_type,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            logger.info("Vision call succeeded with model %s", model)
            return result
        except LLMError as e:
            logger.warning("Vision model %s failed: %s — trying fallback", model, e)
            last_err = e

    raise LLMError(f"All vision models failed: {last_err}")


async def _chat_vision_request(
    system_prompt: str,
    user_prompt: str,
    images: list[bytes],
    image_media_type: str,
    model: str,
    temperature: float,
    max_tokens: int,
) -> Any:
    """Single vision API call — OpenAI multimodal message format."""
    headers = {
        "Authorization": f"Bearer {settings.kymaapi_key}",
        "Content-Type": "application/json",
    }

    # Build content array: text + one image_url block per image
    content: list[dict] = [{"type": "text", "text": user_prompt}]
    for img_bytes in images:
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{image_media_type};base64,{b64}"},
        })

    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": content},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }

    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(KYMA_CHAT_URL, headers=headers, json=payload)

    if resp.status_code != 200:
        logger.error("Vision API error %s (%s): %s", resp.status_code, model, resp.text[:400])
        raise LLMError(f"KymaAPI vision {model} returned {resp.status_code}: {resp.text[:200]}")

    raw = resp.json()["choices"][0]["message"]["content"]
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise LLMError(f"Vision model returned invalid JSON: {e}") from e
