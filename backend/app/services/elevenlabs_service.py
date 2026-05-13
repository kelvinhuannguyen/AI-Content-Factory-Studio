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

    # 1. Gemini 2.5 Flash Native Audio (cheapest, Google-quality)
    try:
        return await _gemini_native_audio(text, language)
    except TTSError as e:
        logger.warning("Gemini Native Audio TTS failed: %s — falling back to ElevenLabs", e)

    # 2. ElevenLabs via KymaAPI /audio/speech
    try:
        return await _elevenlabs_tts(text, language)
    except TTSError as e:
        logger.warning("ElevenLabs TTS failed: %s", e)

    raise TTSError("All TTS providers unavailable")


async def _gemini_native_audio(text: str, language: str) -> bytes:
    """
    Gemini 2.5 Flash Native Audio via KymaAPI /chat/completions.
    Uses OpenAI audio output format: choices[0].message.audio.data (base64 MP3).
    """
    lang_instruction = "Đọc văn bản sau bằng giọng Việt Nam tự nhiên:" if language == "vi" else "Read the following text naturally:"

    headers = {
        "Authorization": f"Bearer {settings.kymaapi_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": _GEMINI_NATIVE_AUDIO_MODEL,
        "messages": [
            {
                "role": "user",
                "content": f"{lang_instruction}\n\n{text}",
            }
        ],
        "modalities": ["audio"],
        "audio": {"format": "mp3"},
    }

    url = f"{settings.kymaapi_base_url}/chat/completions"
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(url, headers=headers, json=payload)

    if resp.status_code != 200:
        raise TTSError(f"Gemini Native Audio {resp.status_code}: {resp.text[:300]}")

    data = resp.json()

    # OpenAI audio output format: choices[0].message.audio.data
    try:
        audio_b64 = data["choices"][0]["message"]["audio"]["data"]
        return base64.b64decode(audio_b64)
    except (KeyError, IndexError, TypeError):
        pass

    # Fallback: content might be base64 directly
    try:
        content = data["choices"][0]["message"]["content"]
        if content and not content.startswith(" ") and len(content) > 100:
            return base64.b64decode(content)
    except Exception:
        pass

    raise TTSError(f"Could not extract audio from Gemini Native Audio response: {str(data)[:200]}")


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
