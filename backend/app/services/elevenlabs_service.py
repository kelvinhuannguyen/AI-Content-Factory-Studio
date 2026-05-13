"""TTS service — ElevenLabs via KymaAPI (primary) with fallback."""
import logging
import httpx
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class TTSError(Exception):
    pass


async def generate_voiceover(text: str, language: str = "vi") -> bytes:
    """
    Generate TTS audio for the given text.
    Returns MP3 bytes.
    Tries KymaAPI eleven-multilingual-v2 first, falls back to basic TTS.
    """
    if not text.strip():
        raise TTSError("Empty text provided for TTS")

    # Primary: KymaAPI → ElevenLabs
    if settings.kymaapi_key:
        try:
            return await _kymaapi_tts(text, language)
        except TTSError as e:
            logger.warning("KymaAPI TTS failed: %s — trying fallback", e)

    raise TTSError("All TTS providers unavailable")


async def _kymaapi_tts(text: str, language: str) -> bytes:
    """KymaAPI /audio/speech — OpenAI-compatible endpoint."""
    # Voice selection by language
    voice_id = _pick_voice(language)

    headers = {
        "Authorization": f"Bearer {settings.kymaapi_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.kymaapi_tts_model,   # eleven-multilingual-v2
        "input": text,
        "voice": voice_id,
    }

    url = f"{settings.kymaapi_base_url}/audio/speech"
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(url, headers=headers, json=payload)

    if resp.status_code != 200:
        raise TTSError(f"KymaAPI TTS {resp.status_code}: {resp.text[:300]}")

    # Response is audio bytes (mp3)
    return resp.content


def _pick_voice(language: str) -> str:
    """Pick ElevenLabs voice_id by language."""
    voice_map = {
        "vi": settings.kymaapi_tts_voice_id,   # Rachel (21m00Tcm4TlvDq8ikWAM) — multilingual
        "en": settings.kymaapi_tts_voice_id,
    }
    return voice_map.get(language, settings.kymaapi_tts_voice_id)
