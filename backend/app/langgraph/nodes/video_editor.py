"""Agent Video Editor — generate clips + voiceover + subtitle + BGM + assemble."""
from __future__ import annotations
import asyncio
import logging
import uuid

from ...services.sse_service import publish_event
from ..state import ProductionState

logger = logging.getLogger(__name__)


async def video_editor_node(state: ProductionState) -> dict:
    """
    Agent Video Editor — full inline pipeline (no Celery needed):
    1. Generate video clips (kling-3-pro, 10s each) — sequential
    2. Generate voiceover (ElevenLabs) + BGM (minimax) — concurrent
    3. Generate subtitle (Whisper) from voiceover audio
    4. Assemble: concat clips → burn subtitle → mix voiceover + BGM
    5. Upload final.mp4 to R2

    All non-critical steps (BGM, subtitle) fail gracefully.
    """
    project_id = state["project_id"]
    retry_count = state.get("video_retry_count", 0)

    await publish_event(project_id, {
        "type": "agent_start",
        "agent": "video_editor",
        "message": f"Bắt đầu tạo video{'(lần ' + str(retry_count + 1) + ')' if retry_count > 0 else ''}...",
    })

    # ── 1. Load scenes from DB ────────────────────────────────────────────
    from ...database import AsyncSessionLocal
    from ...models.scene import Scene
    from ...models.script import Script
    from ...models.project import Project, ProjectStatus
    from sqlalchemy import select

    pid = uuid.UUID(project_id)
    async with AsyncSessionLocal() as db:
        scene_result = await db.execute(
            select(Scene).where(Scene.project_id == pid).order_by(Scene.scene_number)
        )
        scenes = scene_result.scalars().all()

        script_result = await db.execute(
            select(Script).where(Script.project_id == pid).order_by(Script.version.desc())
        )
        script = script_result.scalars().first()
        narration_text = (script.content_raw or "") if script else ""

        proj = await db.get(Project, pid)
        language = proj.preferred_language if proj else "vi"
        aspect_ratio = "9:16" if proj and str(proj.production_type) == "short_video" else "16:9"
        genre = proj.genre or "" if proj else ""
        style = proj.style or "" if proj else ""
        total_duration = proj.duration_seconds or 60 if proj else 60

        if proj:
            proj.status = ProjectStatus.generating
        await db.commit()

    if not scenes:
        await publish_event(project_id, {"type": "agent_error", "agent": "video_editor", "error": "Không có cảnh nào"})
        return {"error": "No scenes found", "current_stage": "video_editor"}

    # ── 1b. Load shots (from cinematic_decomposer) or fall back to scenes ──
    from ...models.shot import Shot as ShotModel
    async with AsyncSessionLocal() as db:
        shot_result = await db.execute(
            select(ShotModel)
            .where(ShotModel.project_id == pid, ShotModel.status == "APPROVED")
            .order_by(ShotModel.scene_id, ShotModel.shot_number)
        )
        shots = shot_result.scalars().all()

    # Use shots if available (cinematic_decomposer ran), else fall back to scenes
    use_shots = len(shots) > 0

    if use_shots:
        clip_items = [
            {
                "id": str(s.id),
                "prompt": s.prompt,
                "duration": min(s.duration, 8),
                "label": s.shot_id,
            }
            for s in shots
        ]
        await publish_event(project_id, {
            "type": "pipeline_queued",
            "shot_count": len(shots),
            "message": f"Đang tạo {len(shots)} shots ≤8s (Cinematic) + giọng đọc + subtitle + nhạc nền...",
        })
    else:
        clip_items = [
            {
                "id": str(s.id),
                "prompt": s.video_prompt or f"Scene {s.scene_number}: {s.description or s.title or ''}",
                "duration": s.duration_seconds or 8,
                "label": f"SC{s.scene_number:02d}",
            }
            for s in scenes
        ]
        await publish_event(project_id, {
            "type": "pipeline_queued",
            "scene_count": len(scenes),
            "message": f"Đang tạo {len(scenes)} clip + giọng đọc + subtitle + nhạc nền...",
        })

    # ── 2. Generate video clips (sequential) ─────────────────────────────
    from ...tasks.video_tasks import _generate_clip_async
    from ...tasks.pipeline_tasks import _MockTask

    for item in clip_items:
        try:
            await _generate_clip_async(
                _MockTask(), project_id, item["id"],
                item["prompt"],
                item["duration"],
                aspect_ratio,
            )
        except Exception as e:
            logger.error("Clip failed %s: %s", item["label"], e)

    # ── 3. Generate voiceover + BGM concurrently ──────────────────────────
    from ...tasks.tts_tasks import _tts_async
    from ...tasks.pipeline_tasks import _MockTask as _MockTask2  # reuse for tts
    from ...services.bgm_service import generate_bgm, BGMError
    from ...services.r2_service import upload_bytes

    voiceover_key: str | None = None
    voiceover_bytes: bytes | None = None
    bgm_key: str | None = None

    async def _do_tts():
        nonlocal voiceover_key, voiceover_bytes
        try:
            voiceover_key = await _tts_async(_MockTask2(), project_id, narration_text, language)
            # Download voiceover bytes for subtitle generation
            if voiceover_key:
                from ...services.r2_service import download_bytes
                voiceover_bytes = await download_bytes(voiceover_key)
        except Exception as e:
            logger.error("Voiceover failed: %s", e)

    async def _do_bgm():
        nonlocal bgm_key
        try:
            bgm_bytes = await generate_bgm(genre, style, total_duration)
            bgm_key = f"projects/{project_id}/bgm.mp3"
            await upload_bytes(bgm_key, bgm_bytes, content_type="audio/mpeg")
            logger.info("BGM generated: %s", bgm_key)
        except (BGMError, Exception) as e:
            logger.warning("BGM generation failed (non-fatal): %s", e)

    await asyncio.gather(_do_tts(), _do_bgm())

    # ── 4. Generate subtitle from voiceover ───────────────────────────────
    from ...services.subtitle_service import generate_subtitles, upload_subtitle

    subtitle_srt = ""
    subtitle_key: str | None = None
    if voiceover_bytes:
        subtitle_srt = await generate_subtitles(voiceover_bytes, language)
        subtitle_key = await upload_subtitle(project_id, subtitle_srt)

    # ── 5. Assemble video ─────────────────────────────────────────────────
    from ...tasks.assembly_tasks import _assemble_async

    final_key: str | None = None
    try:
        final_key = await _assemble_async(
            _MockTask(), project_id, [], voiceover_key, bgm_key,
            subtitle_srt=subtitle_srt,
        )
    except Exception as e:
        logger.error("Assembly failed: %s", e)
        await publish_event(project_id, {"type": "pipeline_error", "error": str(e)})
        return {"error": str(e), "current_stage": "video_editor"}

    await publish_event(project_id, {
        "type": "agent_done",
        "agent": "video_editor",
        "final_video_r2_key": final_key,
        "has_subtitle": bool(subtitle_key),
        "has_bgm": bool(bgm_key),
        "message": "Video đã dựng xong — đang chấm điểm chất lượng...",
    })

    return {
        "final_video_r2_key": final_key,
        "voiceover_r2_key": voiceover_key,
        "subtitle_r2_key": subtitle_key,
        "bgm_r2_key": bgm_key,
        "error": None,
        "current_stage": "video_validator",
    }
