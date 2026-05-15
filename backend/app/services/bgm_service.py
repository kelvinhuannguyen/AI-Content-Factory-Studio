"""Background music generation via KymaAPI minimax-music-pro."""
import asyncio
import logging
import httpx
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_AUDIO_GEN_URL = f"{settings.kymaapi_base_url}/music/generations"
_JOBS_URL = f"{settings.kymaapi_base_url}/jobs"
_POLL_INTERVAL = 8
_MAX_WAIT = 120  # 2 min max for BGM


class BGMError(Exception):
    pass


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.kymaapi_key}",
        "Content-Type": "application/json",
    }


async def generate_bgm(
    genre: str,
    style: str,
    duration_seconds: int,
    motion_intensity_avg: float | None = None,
) -> bytes:
    """
    Generate instrumental background music via minimax-music-pro.
    Returns MP3 bytes. Non-fatal — caller should wrap in try/except.
    motion_intensity_avg (0-10) from continuity_director overrides genre-based mood when provided.
    """
    duration = min(max(duration_seconds, 10), 120)
    mood_map = {
        "hành động": "energetic epic",
        "lãng mạn": "soft romantic",
        "hài hước": "playful upbeat",
        "kinh dị": "dark mysterious",
        "drama": "emotional cinematic",
    }
    mood = mood_map.get(genre.lower(), "upbeat cinematic")

    if motion_intensity_avg is not None:
        if motion_intensity_avg >= 7.5:
            mood = "high-energy intense orchestral, driving percussion, fast tempo"
        elif motion_intensity_avg >= 5.0:
            mood = "dynamic cinematic, building tension, moderate tempo"
        elif motion_intensity_avg >= 2.5:
            mood = "warm emotional underscore, gentle strings, medium pace"
        else:
            mood = "soft ambient atmospheric, minimal instrumentation, slow breath"

    prompt = f"{mood} instrumental background music, {style}, no vocals, loopable"

    payload = {
        "model": settings.kymaapi_music_model,  # minimax-music-pro
        "prompt": prompt,
        "duration": duration,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(_AUDIO_GEN_URL, headers=_headers(), json=payload)

    if resp.status_code not in (200, 202):
        raise BGMError(f"BGM submit {resp.status_code}: {resp.text[:200]}")

    data = resp.json()

    # Sync response
    if "data" in data and data["data"]:
        url = data["data"][0].get("url") or data["data"][0].get("audio_url")
        if url:
            return await _download(url)

    job_id = data.get("id") or data.get("job_id")
    if not job_id:
        raise BGMError(f"No job_id in BGM response: {data}")

    logger.info("BGM job submitted: %s (%ds, genre=%s)", job_id, duration, genre)
    return await _poll_and_download(job_id)


async def _poll_and_download(job_id: str) -> bytes:
    waited = 0
    async with httpx.AsyncClient(timeout=15) as client:
        while waited < _MAX_WAIT:
            resp = await client.get(f"{_JOBS_URL}/{job_id}", headers=_headers())
            if resp.status_code == 200:
                job = resp.json()
                status = job.get("status", "")
                if status == "succeeded":
                    output = job.get("output", {})
                    url = (
                        output.get("url")
                        or output.get("audio_url")
                        or (output.get("data") or [{}])[0].get("url")
                    )
                    if url:
                        return await _download(url)
                    raise BGMError("BGM job succeeded but no audio URL in output")
                if status in ("failed", "cancelled"):
                    raise BGMError(f"BGM job {job_id} {status}")
            await asyncio.sleep(_POLL_INTERVAL)
            waited += _POLL_INTERVAL
    raise BGMError(f"BGM job {job_id} timed out after {_MAX_WAIT}s")


async def _download(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        resp = await client.get(url)
    if resp.status_code != 200:
        raise BGMError(f"BGM download failed {resp.status_code}: {url}")
    return resp.content
