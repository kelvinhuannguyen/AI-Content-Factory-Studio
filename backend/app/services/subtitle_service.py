"""Subtitle generation via Whisper (KymaAPI) + FFmpeg SRT burning."""
import logging
import tempfile
import asyncio
from pathlib import Path
import httpx
from ..config import get_settings
from .r2_service import upload_bytes

logger = logging.getLogger(__name__)
settings = get_settings()

_TRANSCRIPTION_URL = f"{settings.kymaapi_base_url}/audio/transcriptions"


async def generate_subtitles(audio_bytes: bytes, language: str = "vi") -> str:
    """
    Transcribe audio to SRT via KymaAPI Whisper endpoint.
    Returns SRT string, or "" if unavailable (non-fatal).
    """
    if not settings.kymaapi_key or not audio_bytes:
        return ""

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                _TRANSCRIPTION_URL,
                headers={"Authorization": f"Bearer {settings.kymaapi_key}"},
                files={"file": ("voiceover.mp3", audio_bytes, "audio/mpeg")},
                data={
                    "model": "whisper-1",
                    "response_format": "srt",
                    "language": language,
                },
            )
        if resp.status_code == 200 and resp.text.strip():
            logger.info("Subtitles generated: %d chars", len(resp.text))
            return resp.text
        logger.warning("Subtitle transcription %d: %s", resp.status_code, resp.text[:100])
        return ""
    except Exception as e:
        logger.warning("Subtitle generation failed (non-fatal): %s", e)
        return ""


async def upload_subtitle(project_id: str, srt_content: str) -> str | None:
    """Upload SRT file to R2. Returns R2 key or None."""
    if not srt_content.strip():
        return None
    key = f"projects/{project_id}/subtitle.srt"
    try:
        await upload_bytes(key, srt_content.encode("utf-8"), content_type="text/plain")
        return key
    except Exception as e:
        logger.warning("Subtitle upload failed: %s", e)
        return None


async def burn_subtitles_into_video(
    video_bytes: bytes,
    srt_content: str,
    project_id: str,
) -> bytes:
    """
    Burn SRT subtitles into video using FFmpeg.
    Returns video bytes with burned-in subtitles.
    Falls back to original video bytes if FFmpeg fails or libass unavailable.
    """
    if not srt_content.strip():
        return video_bytes

    try:
        with (
            tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as vf,
            tempfile.NamedTemporaryFile(suffix=".srt", delete=False, mode="w", encoding="utf-8") as sf,
            tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as outf,
        ):
            vf.write(video_bytes)
            vf.flush()
            sf.write(srt_content)
            sf.flush()
            in_path = vf.name
            srt_path = sf.name
            out_path = outf.name

        style = "Fontsize=18,PrimaryColour=&Hffffff,OutlineColour=&H000000,Outline=2,MarginV=30,Alignment=2"
        cmd = [
            "ffmpeg", "-y",
            "-i", in_path,
            "-vf", f"subtitles={srt_path}:force_style='{style}'",
            "-c:a", "copy",
            out_path,
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

        if proc.returncode != 0:
            logger.warning("FFmpeg subtitle burn failed: %s", stderr[-300:] if stderr else "")
            return video_bytes  # non-fatal fallback

        burned = Path(out_path).read_bytes()
        logger.info("Subtitles burned into video: %d bytes", len(burned))
        return burned

    except Exception as e:
        logger.warning("Subtitle burn failed (non-fatal): %s", e)
        return video_bytes
    finally:
        for p in [in_path, srt_path, out_path]:
            try:
                Path(p).unlink(missing_ok=True)
            except Exception:
                pass
