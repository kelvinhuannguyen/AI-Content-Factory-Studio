"""TTS service — chain: FPT AI (Vietnamese-native) → MiniMax → ElevenLabs.

FPT AI TTS v5:
  POST https://api.fpt.ai/hmi/tts/v5
  Headers: api-key, speed, voice
  Body: raw UTF-8 text
  Response: {"error": 0, "async": "<mp3_url>", ...}
  Download: GET <mp3_url>

Auto-chunks text > 4800 chars at sentence boundaries.
"""
import asyncio
import re
import logging
import httpx
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_KYMA_TTS_URL  = f"{settings.kymaapi_base_url}/audio/speech"
_FPT_TTS_URL   = "https://api.fpt.ai/hmi/tts/v5"
_MIN_AUDIO_BYTES = 2000
_MAX_CHARS       = 4800   # both FPT and ElevenLabs cap near 5000


class TTSError(Exception):
    pass


# ── Text chunking ─────────────────────────────────────────────────────────────

def _split_text(text: str) -> list[str]:
    """Split text into chunks ≤ _MAX_CHARS at sentence boundaries."""
    if len(text) <= _MAX_CHARS:
        return [text]

    sentences = re.split(r'(?<=[.!?\n。！？])\s*', text)
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        if not sentence:
            continue
        if len(sentence) > _MAX_CHARS:
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


# ── Main entry ────────────────────────────────────────────────────────────────

async def generate_voiceover(text: str, language: str = "vi", narrator_gender: str = "woman") -> bytes:
    """
    Generate TTS. Chain: FPT AI → MiniMax → ElevenLabs.
    narrator_gender: "woman" | "man" — picks FPT voice automatically.
    Auto-chunks long text and concatenates MP3 bytes.
    """
    if not text.strip():
        raise TTSError("Empty text")

    chunks = _split_text(text)
    if len(chunks) > 1:
        logger.info("TTS: %d chars → %d chunks (gender=%s)", len(text), len(chunks), narrator_gender)

    parts: list[bytes] = []
    for i, chunk in enumerate(chunks):
        logger.info("TTS chunk %d/%d (%d chars)", i + 1, len(chunks), len(chunk))
        parts.append(await _generate_chunk(chunk, language, narrator_gender))

    return b"".join(parts)


async def _generate_chunk(text: str, language: str, narrator_gender: str = "woman") -> bytes:
    # 1. FPT AI — native Vietnamese, auto voice by gender
    if language == "vi" and settings.fpt_tts_api_key:
        try:
            return await _fpt_tts(text, narrator_gender)
        except TTSError as e:
            logger.warning("FPT TTS failed: %s — trying MiniMax", e)

    # 2. MiniMax — auto-detects language
    try:
        return await _minimax_tts(text, language)
    except TTSError as e:
        logger.warning("MiniMax TTS failed: %s — trying ElevenLabs", e)

    # 3. ElevenLabs — fallback
    try:
        return await _elevenlabs_tts(text, language)
    except TTSError as e:
        logger.warning("ElevenLabs TTS failed: %s", e)

    raise TTSError("All TTS providers failed")


# ── FPT AI TTS ────────────────────────────────────────────────────────────────

async def _fpt_tts(text: str, narrator_gender: str = "woman") -> bytes:
    """
    FPT AI TTS v5 — Vietnamese-native voices.
    Auto-selects voice by gender: woman→banmai, man→leminh.
    Response: {"error": 0, "async": "<mp3_url>"}
    """
    voice = (
        settings.fpt_tts_voice_male_vi
        if "man" in narrator_gender.lower()
        else settings.fpt_tts_voice_vi
    )
    logger.info("FPT TTS: voice=%s (gender=%s)", voice, narrator_gender)
    headers = {
        "api-key": settings.fpt_tts_api_key,
        "speed": "",
        "voice": voice,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            _FPT_TTS_URL,
            content=text.encode("utf-8"),
            headers=headers,
        )

    if resp.status_code != 200:
        raise TTSError(f"FPT TTS {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    if data.get("error", -1) != 0:
        raise TTSError(f"FPT TTS error: {data}")

    mp3_url = data.get("async")
    if not mp3_url:
        raise TTSError(f"FPT TTS: no async URL in response: {data}")

    logger.info("FPT TTS: downloading from %s", mp3_url)
    return await _download_with_retry(mp3_url)


async def _download_with_retry(url: str, max_attempts: int = 5, delay: float = 2.0) -> bytes:
    """Download FPT audio — may need a brief wait before the file is ready."""
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        for attempt in range(max_attempts):
            resp = await client.get(url)
            if resp.status_code == 200 and len(resp.content) >= _MIN_AUDIO_BYTES:
                logger.info("FPT TTS audio: %d bytes", len(resp.content))
                return resp.content
            logger.debug("FPT TTS download attempt %d: status=%s, size=%d", attempt + 1, resp.status_code, len(resp.content))
            await asyncio.sleep(delay)

    raise TTSError(f"FPT TTS: audio not ready after {max_attempts} attempts: {url}")


# ── MiniMax TTS ───────────────────────────────────────────────────────────────

async def _minimax_tts(text: str, language: str) -> bytes:
    voice = "female-shaonv" if language == "vi" else "male-qn-qingse"
    payload = {"model": "minimax-speech-hd", "input": text, "voice": voice}
    headers = {
        "Authorization": f"Bearer {settings.kymaapi_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(_KYMA_TTS_URL, headers=headers, json=payload)

    if resp.status_code != 200:
        raise TTSError(f"MiniMax TTS {resp.status_code}: {resp.text[:300]}")
    if len(resp.content) < _MIN_AUDIO_BYTES:
        raise TTSError(f"MiniMax response too small ({len(resp.content)}B): {resp.text[:150]}")

    logger.info("MiniMax TTS: %d bytes", len(resp.content))
    return resp.content


# ── ElevenLabs TTS ────────────────────────────────────────────────────────────

async def _elevenlabs_tts(text: str, language: str) -> bytes:
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
        resp = await client.post(_KYMA_TTS_URL, headers=headers, json=payload)

    if resp.status_code != 200:
        raise TTSError(f"ElevenLabs TTS {resp.status_code}: {resp.text[:300]}")
    if len(resp.content) < _MIN_AUDIO_BYTES:
        raise TTSError(f"ElevenLabs too small ({len(resp.content)}B): {resp.text[:150]}")

    logger.info("ElevenLabs TTS: %d bytes", len(resp.content))
    return resp.content
