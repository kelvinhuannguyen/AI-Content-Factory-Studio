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
    sfx_path: Path | None = None,
    sfx_volume: float = 0.05,
) -> None:
    """
    Mix video with voiceover + optional background music + optional SFX ambient.
    Voiceover takes priority; music is ducked to 15%; SFX ambient at 5%.
    """
    audio_inputs = [p for p in [voiceover_path, music_path, sfx_path] if p is not None]
    if not audio_inputs:
        await _run([_FFMPEG, "-y", "-i", str(video_path), "-c", "copy", str(output_path)])
        return

    filter_parts = []
    inputs = ["-i", str(video_path)]
    audio_stream_idx = 1

    if voiceover_path:
        inputs += ["-i", str(voiceover_path)]
        filter_parts.append(f"[{audio_stream_idx}:a]volume={voiceover_volume}[vo]")
        audio_stream_idx += 1
    if music_path:
        inputs += ["-i", str(music_path)]
        filter_parts.append(f"[{audio_stream_idx}:a]volume={music_volume}[bg]")
        audio_stream_idx += 1
    if sfx_path:
        inputs += ["-i", str(sfx_path)]
        filter_parts.append(f"[{audio_stream_idx}:a]volume={sfx_volume}[sfx]")

    # Build mix based on which streams are present
    mix_inputs = (
        (["[vo]"] if voiceover_path else [])
        + (["[bg]"] if music_path else [])
        + (["[sfx]"] if sfx_path else [])
    )
    n = len(mix_inputs)
    if n > 1:
        filter_parts.append(f"{''.join(mix_inputs)}amix=inputs={n}:duration=first[aout]")
        amap = "[aout]"
    else:
        amap = mix_inputs[0]

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


async def xfade_concat(
    clip_bytes_list: list[bytes],
    transition_specs: list[str],
    clip_durations: list[float],
    fade_duration: float = 0.3,
) -> bytes:
    """
    Concatenate clips with cross-dissolve xfade transitions.
    Falls back to stream-copy concat if all transitions are "cut" or on FFmpegError.
    Returns video-only MP4 bytes (no audio — audio mixed separately).
    """
    if len(clip_bytes_list) == 1:
        return clip_bytes_list[0]

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        clip_paths = []
        for i, b in enumerate(clip_bytes_list):
            p = tmp_path / f"clip_{i:03d}.mp4"
            p.write_bytes(b)
            clip_paths.append(p)

        has_xfade = any(t != "cut" for t in transition_specs)
        if not has_xfade:
            out = tmp_path / "out.mp4"
            await concat_video_clips(clip_paths, out)
            return out.read_bytes()

        inputs_args = []
        for p in clip_paths:
            inputs_args += ["-i", str(p)]

        filter_parts = []
        current_label = "[0:v]"
        accumulated_offset = 0.0

        for i in range(len(clip_paths) - 1):
            transition = transition_specs[i] if i < len(transition_specs) else "fade"
            next_label = f"[v{i + 1:03d}]"

            if transition == "cut":
                t_type, t_dur = "fade", 0.001
            else:
                t_type, t_dur = transition, fade_duration

            offset = accumulated_offset + clip_durations[i] - t_dur
            filter_parts.append(
                f"{current_label}[{i + 1}:v]xfade=transition={t_type}:"
                f"duration={t_dur:.3f}:offset={offset:.3f}{next_label}"
            )
            accumulated_offset = offset
            current_label = next_label

        filter_complex = ";".join(filter_parts)
        out = tmp_path / "xfade_out.mp4"
        try:
            await _run([
                _FFMPEG, "-y",
                *inputs_args,
                "-filter_complex", filter_complex,
                "-map", current_label,
                "-an",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                str(out),
            ])
            return out.read_bytes()
        except FFmpegError as e:
            logger.warning("xfade failed, falling back to simple concat: %s", e)
            out2 = tmp_path / "fallback.mp4"
            await concat_video_clips(clip_paths, out2)
            return out2.read_bytes()


async def assemble_with_xfade(
    clip_bytes_list: list[bytes],
    clip_durations: list[float],
    transition_specs: list[str],
    voiceover_bytes: bytes | None,
    music_bytes: bytes | None,
    sfx_bytes: bytes | None = None,
) -> bytes:
    """Full pipeline: xfade concat (video only) → audio mix."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        video_only = await xfade_concat(clip_bytes_list, transition_specs, clip_durations)
        video_path = tmp_path / "video_only.mp4"
        video_path.write_bytes(video_only)

        vo_path = music_path = sfx_path = None
        if voiceover_bytes:
            vo_path = tmp_path / "vo.mp3"
            vo_path.write_bytes(voiceover_bytes)
        if music_bytes:
            music_path = tmp_path / "bgm.mp3"
            music_path.write_bytes(music_bytes)
        if sfx_bytes:
            sfx_path = tmp_path / "sfx.mp3"
            sfx_path.write_bytes(sfx_bytes)

        final_out = tmp_path / "final.mp4"
        await mix_audio_tracks(
            video_path, vo_path, music_path, final_out,
            sfx_path=sfx_path,
        )
        return final_out.read_bytes()


# ── Color grading curves (LUT-equivalent, no .cube files needed) ──────────────

_STYLE_CURVES: dict[str, str] = {
    "cinematic": (
        "curves=r='0/0 0.25/0.22 0.75/0.78 1/1'"
        ":g='0/0 0.5/0.5 1/1'"
        ":b='0/0 0.25/0.28 0.75/0.72 1/1',"
        "eq=contrast=1.08:saturation=0.88"
    ),
    "cyberpunk": (
        "curves=r='0/0 0.4/0.45 1/1'"
        ":b='0/0 0.3/0.4 0.8/0.85 1/1',"
        "eq=contrast=1.25:saturation=1.5:brightness=-0.05"
    ),
    "animation-3d": (
        "eq=contrast=1.1:saturation=1.3:brightness=0.01,"
        "colorbalance=rs=0.05:gs=0.02:bs=-0.05"
    ),
    "vlog": (
        "eq=brightness=0.05:contrast=0.95:saturation=1.15,"
        "colorbalance=rs=0.06:gs=0.02:bs=-0.06"
    ),
}

_GENRE_CURVES: dict[str, str] = {
    "hành động": "eq=contrast=1.15:saturation=1.1",
    "lãng mạn":  "colorbalance=rs=0.1:bs=-0.1,eq=saturation=0.95",
    "kinh dị":   "curves=all='0/0 0.3/0.25 0.7/0.75 1/1',eq=brightness=-0.07",
    "drama":     "eq=contrast=1.05:saturation=0.9",
}


async def apply_color_grade(
    video_bytes: bytes,
    genre: str,
    style: str,
    project_id: str,
) -> bytes:
    """Apply cinematic color grade via curves filter. Non-fatal: returns original on error."""
    style_f = _STYLE_CURVES.get(style.lower(), "")
    genre_f = _GENRE_CURVES.get(genre.lower(), "")
    vf = ",".join(f for f in [style_f, genre_f] if f)
    if not vf:
        return video_bytes

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        in_p  = tmp_path / "in.mp4"
        out_p = tmp_path / "out.mp4"
        in_p.write_bytes(video_bytes)
        try:
            await _run([
                _FFMPEG, "-y", "-i", str(in_p),
                "-vf", vf,
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "copy",
                str(out_p),
            ])
            return out_p.read_bytes()
        except FFmpegError as e:
            logger.warning("Color grade failed (non-fatal, project=%s): %s", project_id, e)
            return video_bytes


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
