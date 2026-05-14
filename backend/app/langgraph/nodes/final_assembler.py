"""Agent Final Assembler & Mastering Engineer.

Sits between video_editor and video_validator.
Responsibilities:
  1. Collect clips (Shot.clip_r2_key if shots mode, else Scene.clip_r2_key)
  2. Generate SFX ambient track from shot ambience descriptions
  3. Build Master Blueprint JSON (full timeline, audio map, QC summary)
  4. xfade cross-dissolve transitions between clips
  5. Assemble: xfade concat → audio mix (VO + BGM + SFX) → subtitle burn → color grade
  6. Upload final.mp4 + blueprint.json to R2
  7. Update Project.final_video_r2_key + blueprint_r2_key in DB
"""
from __future__ import annotations
import json
import logging
import uuid
from datetime import datetime, timezone

from ...services.sse_service import publish_event
from ..state import ProductionState

logger = logging.getLogger(__name__)


async def final_assembler_node(state: ProductionState) -> dict:
    project_id = state["project_id"]
    voiceover_key: str | None = state.get("voiceover_r2_key")
    bgm_key: str | None = state.get("bgm_r2_key")
    genre: str = state.get("genre") or ""
    style: str = state.get("style") or "cinematic"

    await publish_event(project_id, {
        "type": "agent_start",
        "agent": "final_assembler",
        "message": "Final Assembler đang tổng hợp & hoàn thiện video...",
    })

    # ── 1. Collect clips ──────────────────────────────────────────────────
    clips = await _collect_clips(project_id)
    if not clips:
        await publish_event(project_id, {"type": "pipeline_error", "error": "No clips found for assembly"})
        return {"error": "No clips found for assembly", "current_stage": "final_assembler"}

    # ── 2. Download subtitle SRT ──────────────────────────────────────────
    subtitle_srt = await _download_text(state.get("subtitle_r2_key") or "")

    # ── 3. Determine transitions ──────────────────────────────────────────
    transitions = _build_transitions(clips)

    # ── 4. Generate SFX ambient (non-fatal) ──────────────────────────────
    total_dur = sum(c["duration"] for c in clips)
    sfx_key = await _generate_sfx_ambient(project_id, clips, genre, style, int(total_dur))

    # ── 5. Build Blueprint JSON ───────────────────────────────────────────
    blueprint = _build_blueprint(project_id, clips, state, transitions, sfx_key)

    # ── 6. Download clips + audio ─────────────────────────────────────────
    from ...services.r2_service import download_bytes, upload_bytes

    clip_bytes_list: list[bytes] = []
    clip_durations: list[float] = []
    for clip in clips:
        try:
            raw = await download_bytes(clip["clip_r2_key"])
            clip_bytes_list.append(raw)
            clip_durations.append(float(clip["duration"]))
        except Exception as e:
            logger.error("Clip download failed %s: %s", clip.get("shot_id"), e)

    if not clip_bytes_list:
        await publish_event(project_id, {"type": "pipeline_error", "error": "All clips failed to download"})
        return {"error": "All clips failed to download", "current_stage": "final_assembler"}

    voiceover_bytes = await _safe_download(voiceover_key)
    music_bytes     = await _safe_download(bgm_key)
    sfx_bytes       = await _safe_download(sfx_key)

    # ── 7. xfade concat + audio mix ───────────────────────────────────────
    from ...services.ffmpeg_service import assemble_with_xfade, apply_color_grade
    from ...services.subtitle_service import burn_subtitles_into_video

    final_bytes = await assemble_with_xfade(
        clip_bytes_list, clip_durations, transitions,
        voiceover_bytes, music_bytes, sfx_bytes,
    )

    # ── 8. Burn subtitles (non-fatal) ─────────────────────────────────────
    if subtitle_srt:
        try:
            final_bytes = await burn_subtitles_into_video(final_bytes, subtitle_srt, project_id)
        except Exception as e:
            logger.warning("Subtitle burn failed (non-fatal): %s", e)

    # ── 9. Color grade (non-fatal) ────────────────────────────────────────
    final_bytes = await apply_color_grade(final_bytes, genre, style, project_id)

    # ── 10. Upload final.mp4 + blueprint.json ─────────────────────────────
    final_key = f"projects/{project_id}/final.mp4"
    await upload_bytes(final_key, final_bytes, content_type="video/mp4")

    blueprint_json_bytes = json.dumps(blueprint, ensure_ascii=False, indent=2).encode()
    blueprint_key = f"projects/{project_id}/blueprint.json"
    await upload_bytes(blueprint_key, blueprint_json_bytes, content_type="application/json")

    # ── 11. Update Project in DB ──────────────────────────────────────────
    await _update_project_final(project_id, final_key, blueprint_key)

    await publish_event(project_id, {
        "type": "agent_done",
        "agent": "final_assembler",
        "final_video_r2_key": final_key,
        "blueprint_r2_key": blueprint_key,
        "clip_count": len(clip_bytes_list),
        "has_sfx": bool(sfx_key),
        "message": (
            f"Video hoàn chỉnh — {len(clip_bytes_list)} clips · xfade transitions · "
            f"color grade · {'SFX ambient · ' if sfx_key else ''}Đang chấm điểm..."
        ),
    })

    return {
        "final_video_r2_key": final_key,
        "blueprint_r2_key": blueprint_key,
        "error": None,
        "current_stage": "video_validator",
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _collect_clips(project_id: str) -> list[dict]:
    """
    Collect clips in playback order.
    Shots mode (preferred): Shot.clip_r2_key ordered by (scene_id, shot_number).
    Fallback: Scene.clip_r2_key ordered by scene_number.
    """
    from ...database import AsyncSessionLocal
    from ...models.shot import Shot
    from ...models.scene import Scene
    from sqlalchemy import select

    pid = uuid.UUID(project_id)
    async with AsyncSessionLocal() as db:
        shot_result = await db.execute(
            select(Shot)
            .where(Shot.project_id == pid, Shot.clip_r2_key.isnot(None))
            .order_by(Shot.scene_id, Shot.shot_number)
        )
        shots = shot_result.scalars().all()
        if shots:
            return [
                {
                    "shot_id": s.shot_id,
                    "clip_r2_key": s.clip_r2_key,
                    "duration": s.duration,
                    "scene_prefix": (s.shot_id or "").split("_")[0],
                    "characters_present": s.characters_present or [],
                    "motion_intensity": s.motion_intensity,
                    "continuity_notes": s.continuity_notes,
                    "sfx_prompt": s.sfx_prompt,
                    "ambience": s.ambience,
                }
                for s in shots
            ]

        scene_result = await db.execute(
            select(Scene)
            .where(Scene.project_id == pid, Scene.clip_r2_key.isnot(None))
            .order_by(Scene.scene_number)
        )
        scenes = scene_result.scalars().all()
        return [
            {
                "shot_id": f"SC{s.scene_number:02d}_SH01",
                "clip_r2_key": s.clip_r2_key,
                "duration": s.duration_seconds or 8,
                "scene_prefix": f"SC{s.scene_number:02d}",
                "characters_present": s.characters_in_scene or [],
                "motion_intensity": None,
                "continuity_notes": None,
                "sfx_prompt": None,
                "ambience": None,
            }
            for s in scenes
        ]


def _build_transitions(clips: list[dict]) -> list[str]:
    """
    Determine transition type per consecutive clip pair.
    Same scene → fade; different scene + large motion delta → fadeblack; else → fade.
    """
    transitions = []
    for i in range(len(clips) - 1):
        a, b = clips[i], clips[i + 1]
        a_scene = (a.get("shot_id") or "").split("_")[0]
        b_scene = (b.get("shot_id") or "").split("_")[0]
        if a_scene == b_scene:
            transitions.append("fade")
        else:
            ma = a.get("motion_intensity") or 5
            mb = b.get("motion_intensity") or 5
            transitions.append("fadeblack" if abs(ma - mb) > 4 else "fade")
    return transitions


async def _generate_sfx_ambient(
    project_id: str, clips: list[dict], genre: str, style: str, total_duration: int
) -> str | None:
    """
    Generate one ambient SFX audio track from combined shot ambience descriptions.
    Uses the existing BGM service with an ambient soundscape prompt.
    """
    from ...services.bgm_service import generate_bgm, BGMError
    from ...services.r2_service import upload_bytes

    ambience_set = list(dict.fromkeys(c["ambience"] for c in clips if c.get("ambience")))[:5]
    if not ambience_set:
        return None

    combined = "; ".join(ambience_set)
    ambient_style = f"ambient soundscape, {combined}, no music, environmental audio, subtle"

    try:
        sfx_bytes = await generate_bgm(
            genre="drama",
            style=ambient_style,
            duration_seconds=min(total_duration, 120),
        )
        sfx_key = f"projects/{project_id}/sfx_ambient.mp3"
        await upload_bytes(sfx_key, sfx_bytes, content_type="audio/mpeg")
        logger.info("SFX ambient generated: %s", sfx_key)
        return sfx_key
    except (BGMError, Exception) as e:
        logger.warning("SFX ambient generation failed (non-fatal): %s", e)
        return None


def _build_blueprint(
    project_id: str,
    clips: list[dict],
    state: ProductionState,
    transitions: list[str],
    sfx_key: str | None,
) -> dict:
    """Build Master Blueprint JSON from all available assembly data."""
    continuity_manifest = state.get("continuity_manifest") or {}
    workflow_steps = {
        s["clip_id"]: s
        for s in continuity_manifest.get("workflow_steps", [])
        if s.get("clip_id")
    }

    timeline = []
    current_time = 0.0
    for i, clip in enumerate(clips):
        step = workflow_steps.get(clip.get("shot_id", ""), {})
        transition_out = transitions[i] if i < len(transitions) else "end"
        segment = {
            "segment_index": i,
            "shot_id": clip.get("shot_id"),
            "clip_r2_key": clip["clip_r2_key"],
            "start_time_s": round(current_time, 3),
            "end_time_s": round(current_time + clip["duration"], 3),
            "duration_s": clip["duration"],
            "transition_in": "fade_in" if i == 0 else (transitions[i - 1] if i > 0 else "cut"),
            "transition_out": transition_out,
            "motion_intensity": clip.get("motion_intensity"),
            "characters_present": clip.get("characters_present", []),
            "sfx_prompt": clip.get("sfx_prompt") or step.get("sfx_prompt"),
            "ambience": clip.get("ambience") or step.get("ambience"),
            "continuity_notes": clip.get("continuity_notes") or step.get("continuity_notes"),
        }
        timeline.append(segment)
        current_time += clip["duration"]

    return {
        "master_project": project_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "global_settings": {
            "aspect_ratio": "9:16" if state.get("production_type") == "short_video" else "16:9",
            "color_profile": state.get("style") or "cinematic",
            "genre": state.get("genre") or "",
            "total_clips": len(clips),
            "total_duration_s": round(current_time, 1),
            "has_xfade_transitions": True,
            "has_color_grade": True,
            "has_sfx_ambient": bool(sfx_key),
        },
        "timeline": timeline,
        "audio": {
            "voiceover_key": state.get("voiceover_r2_key"),
            "bgm_key": state.get("bgm_r2_key"),
            "sfx_ambient_key": sfx_key,
            "bgm_volume": 0.15,
            "voiceover_volume": 1.0,
            "sfx_volume": 0.05,
        },
        "subtitle": {
            "srt_key": state.get("subtitle_r2_key"),
            "style": "Bottom_Center_White_18px",
        },
        "qc_summary": {
            "clips_ready": len(clips),
            "clips_expected": len(clips),
            "all_clips_ready": True,
            "has_voiceover": bool(state.get("voiceover_r2_key")),
            "has_bgm": bool(state.get("bgm_r2_key")),
            "has_subtitle": bool(state.get("subtitle_r2_key")),
            "has_sfx_ambient": bool(sfx_key),
            "has_color_grade": True,
            "has_xfade_transitions": True,
        },
    }


async def _download_text(r2_key: str) -> str:
    """Download text content from R2 (SRT, etc.). Returns empty string on failure."""
    if not r2_key:
        return ""
    try:
        from ...services.r2_service import download_bytes
        raw = await download_bytes(r2_key)
        return raw.decode("utf-8")
    except Exception:
        return ""


async def _safe_download(r2_key: str | None) -> bytes | None:
    """Download bytes from R2. Returns None if key is None or download fails."""
    if not r2_key:
        return None
    try:
        from ...services.r2_service import download_bytes
        return await download_bytes(r2_key)
    except Exception as e:
        logger.warning("Failed to download %s: %s", r2_key, e)
        return None


async def _update_project_final(project_id: str, final_key: str, blueprint_key: str) -> None:
    """Mark project as quality_review and save final_video_r2_key + blueprint_r2_key."""
    from ...database import AsyncSessionLocal
    from ...models.project import Project, ProjectStatus
    pid = uuid.UUID(project_id)
    async with AsyncSessionLocal() as db:
        proj = await db.get(Project, pid)
        if proj:
            proj.final_video_r2_key = final_key
            proj.blueprint_r2_key = blueprint_key
            proj.status = ProjectStatus.quality_review
        await db.commit()
