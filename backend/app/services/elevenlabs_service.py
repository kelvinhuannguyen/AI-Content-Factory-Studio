"""TTS service — MiniMax (primary, Vietnamese support) → ElevenLabs (fallback).

MiniMax minimax-speech-hd auto-detects language from text content,
so Vietnamese text produces Vietnamese audio regardless of voice style.

Confirmed working on KymaAPI (2026-05-13):
  - minimax-speech-hd: female-shaonv, male-qn-qingse
  - eleven-multilingual-v2: voice_id 21m00Tcm4TlvDq8ikWAM (Rachel, English-accented)
"""
import logging
import httpx
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_TTS_URL = f"{settings.kymaapi_base_url}/audio/speech"
_MIN_AUDIO_BYTES = 2000   # guard against JSON error responses disguised as 200


class TTSError(Exception):
    pass


async def generate_voiceover(text: str, language: str = "vi") -> bytes:
    """
    Generate TTS audio. Returns MP3 bytes.
    Chain: MiniMax (primary, Vietnamese-ready) → ElevenLabs (fallback)
    """
    if not text.strip():
        raise TTSError("Empty text provided for TTS")
    if not settings.kymaapi_key:
        raise TTSError("KYMAAPI_KEY not configured")

    try:
        return await _minimax_tts(text, language)
    except TTSError as e:
        logger.warning("MiniMax TTS failed: %s — falling back to ElevenLabs", e)

    try:
        return await _elevenlabs_tts(text, language)
    except TTSError as e:
        logger.warning("ElevenLabs TTS failed: %s", e)

    raise TTSError("All TTS providers unavailable")


async def _minimax_tts(text: str, language: str) -> bytes:
    """
    MiniMax speech-hd via KymaAPI /audio/speech.
    Model auto-detects language — Vietnamese text → Vietnamese audio.
    Voice determines style; female-shaonv confirmed working on KymaAPI.
    """
    voice = "female-shaonv" if language == "vi" else "male-qn-qingse"

    payload = {
        "model": "minimax-speech-hd",
        "input": text,
        "voice": voice,
    }
    headers = {
        "Authorization": f"Bearer {settings.kymaapi_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(_TTS_URL, headers=headers, json=payload)

    if resp.status_code != 200:
        raise TTSError(f"MiniMax TTS {resp.status_code}: {resp.text[:300]}")

    if len(resp.content) < _MIN_AUDIO_BYTES:
        raise TTSError(
            f"MiniMax TTS response too small ({len(resp.content)}B) — likely an error: {resp.text[:150]}"
        )

    logger.info("MiniMax TTS: %d bytes (lang=%s, voice=%s)", len(resp.content), language, voice)
    return resp.content


async def _elevenlabs_tts(text: str, language: str) -> bytes:
    """ElevenLabs eleven-multilingual-v2 via KymaAPI /audio/speech (fallback)."""
    payload = {
        "model": settings.kymaapi_tts_model,   # eleven-multilingual-v2
        "input": text,
        "voice": settings.kymaapi_tts_voice_id, # 21m00Tcm4TlvDq8ikWAM
    }
    headers = {
        "Authorization": f"Bearer {settings.kymaapi_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(_TTS_URL, headers=headers, json=payload)

    if resp.status_code != 200:
        raise TTSError(f"ElevenLabs TTS {resp.status_code}: {resp.text[:300]}")

    if len(resp.content) < _MIN_AUDIO_BYTES:
        raise TTSError(
            f"ElevenLabs TTS response too small ({len(resp.content)}B): {resp.text[:150]}"
        )

    logger.info("ElevenLabs TTS fallback: %d bytes", len(resp.content))
    return resp.content
