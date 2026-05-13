"""FFmpeg service — video assembly: concat clips + mix voiceover + music."""
import asyncio
import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_FFMPEG = "ffmpeg"   # expects ffmpeg in PATH (Docker: pre-installed; local: install separately)


class FFmpegError(Exception):
    pass


async def _run(cmd: list[str]) -> None:
    """Run ffmpeg command async, raise on non-zero exit."""
    logger.debug("FFmpeg: %s", " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise FFmpegError(f"ffmpeg failed (exit {proc.returncode}): {stderr.decode()[-500:]}")


async def concat_video_clips(clip_paths: list[Path], output_path: Path) -> None:
    """Concatenate MP4 clips in order using a concat list file."""
    if not clip_paths:
        raise FFmpegError("No clips to concatenate")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for p in clip_paths:
            f.write(f"file '{p.as_posix()}'\n")
        list_file = f.name

    try:
        await _run([
            _FFMPEG, "-y",
            "-f", "concat", "-safe", "0",
            "-i", list_file,
            "-c", "copy",
            str(output_path),
        ])
    finally:
        os.unlink(list_file)


async def mix_audio_tracks(
    video_path: Path,
    voiceover_path: Path | None,
    music_path: Path | None,
    output_path: Path,
    voiceover_volume: float = 1.0,
    music_volume: float = 0.15,
) -> None:
    """
    Mix video with voiceover + optional background music.
    Voiceover takes priority; music is ducked to 15% volume.
    """
    if voiceover_path is None and music_path is None:
        # No audio — just copy video
        await _run([_FFMPEG, "-y", "-i", str(video_path), "-c", "copy", str(output_path)])
        return

    filter_parts = []
    inputs = ["-i", str(video_path)]

    if voiceover_path:
        inputs += ["-i", str(voiceover_path)]
        filter_parts.append(f"[1:a]volume={voiceover_volume}[vo]")
    if music_path:
        inputs += ["-i", str(music_path)]
        idx = 2 if voiceover_path else 1
        filter_parts.append(f"[{idx}:a]volume={music_volume}[bg]")

    # Mix all audio streams
    if voiceover_path and music_path:
        filter_parts.append("[vo][bg]amix=inputs=2:duration=first[aout]")
        amap = "[aout]"
    elif voiceover_path:
        amap = "[vo]"
    else:
        amap = "[bg]"

    filter_complex = ";".join(filter_parts)

    await _run([
        _FFMPEG, "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "0:v",
        "-map", amap,
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(output_path),
    ])


async def assemble_video(
    clip_bytes_list: list[bytes],   # MP4 bytes per scene, in order
    voiceover_bytes: bytes | None,
    music_bytes: bytes | None,
) -> bytes:
    """
    Full assembly pipeline:
    1. Write clips to temp files
    2. Concatenate clips
    3. Mix audio (voiceover + music)
    4. Return final MP4 bytes
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # Write clips
        clip_paths = []
        for i, clip in enumerate(clip_bytes_list):
            p = tmp_path / f"clip_{i:03d}.mp4"
            p.write_bytes(clip)
            clip_paths.append(p)

        # Concatenate
        concat_out = tmp_path / "concat.mp4"
        await concat_video_clips(clip_paths, concat_out)

        # Write audio files
        vo_path = None
        if voiceover_bytes:
            vo_path = tmp_path / "voiceover.mp3"
            vo_path.write_bytes(voiceover_bytes)

        music_path = None
        if music_bytes:
            music_path = tmp_path / "music.mp3"
            music_path.write_bytes(music_bytes)

        # Mix audio
        final_out = tmp_path / "final.mp4"
        await mix_audio_tracks(concat_out, vo_path, music_path, final_out)

        return final_out.read_bytes()


async def extract_keyframe(video_path: Path, time_offset: float = 1.0) -> bytes:
    """Extract a single frame from video at time_offset seconds. Returns JPEG bytes."""
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        out = f.name
    try:
        await _run([
            _FFMPEG, "-y",
            "-ss", str(time_offset),
            "-i", str(video_path),
            "-frames:v", "1",
            "-q:v", "3",
            out,
        ])
        return Path(out).read_bytes()
    finally:
        try:
            os.unlink(out)
        except FileNotFoundError:
            pass
