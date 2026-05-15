"""TTS service — MiniMax (primary, Vietnamese) → ElevenLabs (fallback).

Auto-chunks long text (>4800 chars) at sentence boundaries and concatenates MP3 bytes.
MiniMax minimax-speech-hd auto-detects language from text content.
"""
import re
import logging
import httpx
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_TTS_URL       = f"{settings.kymaapi_base_url}/audio/speech"
_MIN_AUDIO_BYTES = 2000   # guard against JSON error responses disguised as 200
_MAX_CHARS     = 4800     # MiniMax + ElevenLabs both cap at 5000; leave 200 buffer


class TTSError(Exception):
    pass


def _split_text(text: str) -> list[str]:
    """Split text into chunks ≤ _MAX_CHARS at sentence boundaries."""
    if len(text) <= _MAX_CHARS:
        return [text]

    # Split on sentence-ending punctuation followed by whitespace
    sentences = re.split(r'(?<=[.!?\n。！？])\s*', text)
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        if not sentence:
            continue
        if len(sentence) > _MAX_CHARS:
            # Single sentence too long — split on comma or space
            sub_parts = re.split(r'(?<=[,،،،،،،،،،，、])\s*', sentence)
            for part in sub_parts:
                if len(current) + len(part) + 1 > _MAX_CHARS:
                    if current:
                        chunks.append(current.strip())
                    current = part
                else:
                    current = (current + " " + part).strip() if current else part
        elif len(current) + len(sentence) + 1 > _MAX_CHARS:
            if current:
                chunks.append(current.strip())
            current = sentence
        else:
            current = (current + " " + sentence).strip() if current else sentence

    if current:
        chunks.append(current.strip())

    return [c for c in chunks if c]


async def generate_voiceover(text: str, language: str = "vi") -> bytes:
    """
    Generate TTS audio. Returns MP3 bytes (chunks concatenated if text > 4800 chars).
    Chain: MiniMax (primary, Vietnamese-ready) → ElevenLabs (fallback)
    """
    if not text.strip():
        raise TTSError("Empty text provided for TTS")
    if not settings.kymaapi_key:
        raise TTSError("KYMAAPI_KEY not configured")

    chunks = _split_text(text)
    if len(chunks) > 1:
        logger.info("TTS: splitting %d chars into %d chunks", len(text), len(chunks))

    parts: list[bytes] = []
    for i, chunk in enumerate(chunks):
        logger.info("TTS chunk %d/%d (%d chars)", i + 1, len(chunks), len(chunk))
        audio = await _generate_chunk(chunk, language)
        parts.append(audio)

    return b"".join(parts)


async def _generate_chunk(text: str, language: str) -> bytes:
    """Generate TTS for a single chunk — MiniMax primary, ElevenLabs fallback."""
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
    """MiniMax speech-hd via KymaAPI /audio/speech."""
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
        raise TTSError(f"MiniMax TTS response too small ({len(resp.content)}B): {resp.text[:150]}")

    logger.info("MiniMax TTS: %d bytes (lang=%s, voice=%s)", len(resp.content), language, voice)
    return resp.content


async def _elevenlabs_tts(text: str, language: str) -> bytes:
    """ElevenLabs eleven-multilingual-v2 via KymaAPI (fallback)."""
    payload = {
        "model": settings.kymaapi_tts_model,
        "input": text,
        "voice": settings.kymaapi_tts_voice_id,
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
        raise TTSError(f"ElevenLabs TTS too small ({len(resp.content)}B): {resp.text[:150]}")

    logger.info("ElevenLabs TTS fallback: %d bytes", len(resp.content))
    return resp.content
