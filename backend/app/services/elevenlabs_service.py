"""TTS service — Gemini Native Audio (primary, cheap) → ElevenLabs fallback."""
import base64
import logging
import httpx
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_GEMINI_NATIVE_AUDIO_MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"


class TTSError(Exception):
    pass


async def generate_voiceover(text: str, language: str = "vi") -> bytes:
    """
    Generate TTS audio. Returns MP3 bytes.
    Chain: Gemini Native Audio → ElevenLabs (eleven-multilingual-v2)
    """
    if not text.strip():
        raise TTSError("Empty text provided for TTS")

    if not settings.kymaapi_key:
        raise TTSError("KYMAAPI_KEY not configured")

    # 1. ElevenLabs eleven-multilingual-v2 (primary — confirmed working for Vietnamese)
    try:
        return await _elevenlabs_tts(text, language)
    except TTSError as e:
        logger.warning("ElevenLabs TTS failed: %s — falling back to Gemini Native Audio", e)

    # 2. Gemini 2.5 Flash Native Audio (fallback — cheaper but Vietnamese support unverified)
    try:
        return await _gemini_native_audio(text, language)
    except TTSError as e:
        logger.warning("Gemini Native Audio TTS failed: %s", e)

    raise TTSError("All TTS providers unavailable")


async def _gemini_native_audio(text: str, language: str) -> bytes:
    """
    Gemini 2.5 Flash Native Audio via KymaAPI.
    Try A: /audio/speech (OpenAI TTS endpoint — returns audio bytes directly)
    Try B: /chat/completions (basic format per KymaAPI docs) — parse audio from response
    """
    headers = {
        "Authorization": f"Bearer {settings.kymaapi_key}",
        "Content-Type": "application/json",
    }
    lang_instruction = (
        "Đọc văn bản sau bằng giọng tiếng Việt tự nhiên, rõ ràng:"
        if language == "vi"
        else "Read the following text naturally and clearly:"
    )

    # Try A: /audio/speech endpoint (cleanest for TTS — returns audio bytes)
    try:
        payload_a = {
            "model": _GEMINI_NATIVE_AUDIO_MODEL,
            "input": text,
            "voice": "Aoede",  # Gemini default voice
        }
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{settings.kymaapi_base_url}/audio/speech",
                headers=headers, json=payload_a,
            )
        if resp.status_code == 200 and len(resp.content) > 1000:
            logger.info("Gemini Native Audio via /audio/speech: %d bytes", len(resp.content))
            return resp.content
        logger.debug("Gemini /audio/speech returned %d: %s", resp.status_code, resp.text[:100])
    except Exception as e:
        logger.debug("Gemini /audio/speech error: %s", e)

    # Try B: /chat/completions (as shown in KymaAPI docs)
    payload_b = {
        "model": _GEMINI_NATIVE_AUDIO_MODEL,
        "messages": [
            {"role": "user", "content": f"{lang_instruction}\n\n{text}"}
        ],
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{settings.kymaapi_base_url}/chat/completions",
            headers=headers, json=payload_b,
        )

    if resp.status_code != 200:
        raise TTSError(f"Gemini Native Audio chat {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    logger.debug("Gemini Native Audio chat response keys: %s", list(data.get("choices", [{}])[0].get("message", {}).keys()))

    # OpenAI audio output: choices[0].message.audio.data (base64)
    try:
        audio_b64 = data["choices"][0]["message"]["audio"]["data"]
        return base64.b64decode(audio_b64)
    except (KeyError, IndexError, TypeError):
        pass

    # Some providers put base64 audio directly in content
    try:
        content = data["choices"][0]["message"]["content"] or ""
        if len(content) > 500 and not content.strip().startswith("{"):
            decoded = base64.b64decode(content + "==")
            if len(decoded) > 1000:
                return decoded
    except Exception:
        pass

    raise TTSError(
        f"Gemini Native Audio: cannot extract audio bytes. "
        f"Response keys: {list(data.get('choices', [{}])[0].get('message', {}).keys())}"
    )


async def _elevenlabs_tts(text: str, language: str) -> bytes:
    """ElevenLabs eleven-multilingual-v2 via KymaAPI /audio/speech."""
    voice_id = settings.kymaapi_tts_voice_id  # Rachel — multilingual

    headers = {
        "Authorization": f"Bearer {settings.kymaapi_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.kymaapi_tts_model,  # eleven-multilingual-v2
        "input": text,
        "voice": voice_id,
    }

    url = f"{settings.kymaapi_base_url}/audio/speech"
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(url, headers=headers, json=payload)

    if resp.status_code != 200:
        raise TTSError(f"ElevenLabs TTS {resp.status_code}: {resp.text[:300]}")

    return resp.content
