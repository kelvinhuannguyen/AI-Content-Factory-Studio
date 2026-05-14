"""Agent Cinematic Scene Decomposer — between scene_review and video_editor.

Workflow:
1. Build Character Lookbook from approved character DB rows (Visual Anchors)
2. For each approved scene: call Claude with CINEMATIC_DECOMPOSER_SYSTEM
   - Shot Slicing: scene → N shots ≤8s, each with ONE action focus
   - Character Consistency: embed Lookbook Ref IDs + core traits in every shot
   - Production Formula: [Style&Mood]+[Camera]+[Character&ID]+[Lighting]+[Motion]
   - Self-QC: Claude scores ≥8 → APPROVED; <8 → self-refine; still <8 → REJECTED
3. Save APPROVED shots to DB (Shot model)
4. video_editor_node reads shots instead of scenes → better motion coherence
"""
from __future__ import annotations
import logging
import uuid

from ...services.llm_service import chat_json, LLMError
from ...services.sse_service import publish_event
from ...utils.prompt_templates import CINEMATIC_DECOMPOSER_SYSTEM, cinematic_decomposer_user
from ..state import ProductionState

logger = logging.getLogger(__name__)


async def cinematic_decomposer_node(state: ProductionState) -> dict:
    """
    Cinematic Scene Decomposer node.
    Runs after scene_review approval, before video_editor.
    """
    project_id = state["project_id"]
    character_vis_map = state.get("character_vis_map") or {}

    await publish_event(project_id, {
        "type": "agent_start",
        "agent": "cinematic_decomposer",
        "message": "Cinematic Director đang phân rã cảnh quay thành shots ≤8s...",
    })

    # Step 1: Build Character Lookbook from DB
    lookbook = await _build_character_lookbook(project_id, character_vis_map)

    # Step 2: Load approved scenes from DB
    scenes = await _load_approved_scenes(project_id)

    if not scenes:
        logger.warning("cinematic_decomposer: no scenes found — skipping")
        await publish_event(project_id, {
            "type": "agent_done",
            "agent": "cinematic_decomposer",
            "shot_count": 0,
            "message": "Không có cảnh nào để phân rã.",
        })
        return {"shots": [], "lookbook": lookbook, "current_stage": "cinematic_decomposer"}

    # Step 3: Clear old shots
    await _clear_shots(project_id)

    # Step 4: Decompose each scene concurrently (but save results in order)
    import asyncio
    decomposed = await asyncio.gather(*[
        _decompose_scene(scene, lookbook, state) for scene in scenes
    ])

    # Step 5: Save shots to DB and collect all
    all_shots: list[dict] = []
    for scene, shot_dicts in zip(scenes, decomposed):
        saved = await _save_shots(scene["id"], project_id, shot_dicts)
        all_shots.extend(saved)

    approved_count = sum(1 for s in all_shots if s.get("status") == "APPROVED")

    await publish_event(project_id, {
        "type": "agent_done",
        "agent": "cinematic_decomposer",
        "scene_count": len(scenes),
        "shot_count": len(all_shots),
        "approved_count": approved_count,
        "message": f"Phân rã {len(scenes)} cảnh thành {len(all_shots)} shots — {approved_count} APPROVED.",
    })

    logger.info(
        "cinematic_decomposer: %d scenes → %d shots (%d approved)",
        len(scenes), len(all_shots), approved_count,
    )

    return {
        "shots": all_shots,
        "lookbook": lookbook,
        "current_stage": "cinematic_decomposer",
    }


# ── Lookbook Builder ─────────────────────────────────────────────────────────

async def _build_character_lookbook(project_id: str, character_vis_map: dict) -> dict:
    """
    Build Visual Anchors dict from approved characters in DB.
    Merges DB data (physical_dna, color_palette, images) with vis_map.

    Returns:
    {
      "#CHAR_01": {
        "ref_id": "#CHAR_01",
        "name": "Minh Tuân",
        "key_identifier": "Vietnamese man, 28-32, jet black hair...",
        "constant_elements": ["jet black short hair", "scar above left eyebrow"],
        "color_palette": {"primary": "#1a3a5c"},
        "image_url": "https://...",
        "sheet_url": "https://..."
      }
    }
    """
    try:
        from ...database import AsyncSessionLocal
        from ...models.character import Character
        from ...services.r2_service import public_url
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Character)
                .where(
                    Character.project_id == uuid.UUID(project_id),
                    Character.variant_index == 0,
                )
                .order_by(Character.character_index)
            )
            chars = result.scalars().all()

        lookbook: dict = {}
        for c in chars:
            ref_id = c.ref_id or f"#CHAR_0{c.character_index + 1}"
            dna = c.physical_dna or {}

            # Build constant_elements from physical_dna semantic invariants
            constant_elements: list[str] = []
            for field in ["hair_color", "hair_style", "eye_color", "distinctive_features"]:
                val = dna.get(field, "")
                if val and val.lower() not in ("none", "n/a", ""):
                    if field == "hair_color":
                        constant_elements.append(f"{val} hair")
                    elif field == "hair_style":
                        constant_elements.append(f"{val} hairstyle")
                    elif field == "eye_color":
                        constant_elements.append(f"{val} eyes")
                    elif field == "distinctive_features":
                        constant_elements.append(val)

            key_identifier = c.visual_identity_string or character_vis_map.get(ref_id, "")

            lookbook[ref_id] = {
                "ref_id": ref_id,
                "name": c.name or "",
                "key_identifier": key_identifier,
                "constant_elements": constant_elements,
                "color_palette": c.color_palette or {},
                "image_url": public_url(c.image_r2_key) if c.image_r2_key else None,
                "sheet_url": public_url(c.sheet_r2_key) if c.sheet_r2_key else None,
            }

        # Fill in any ref_ids from vis_map that don't have a DB entry (edge case)
        for ref_id, vis in character_vis_map.items():
            if ref_id not in lookbook:
                lookbook[ref_id] = {
                    "ref_id": ref_id,
                    "name": ref_id,
                    "key_identifier": vis,
                    "constant_elements": [],
                    "color_palette": {},
                    "image_url": None,
                    "sheet_url": None,
                }

        return lookbook

    except Exception as e:
        logger.warning("_build_character_lookbook failed: %s — using vis_map fallback", e)
        return {
            ref_id: {
                "ref_id": ref_id,
                "name": ref_id,
                "key_identifier": vis,
                "constant_elements": [],
                "color_palette": {},
                "image_url": None,
                "sheet_url": None,
            }
            for ref_id, vis in character_vis_map.items()
        }


# ── Scene Loading ────────────────────────────────────────────────────────────

async def _load_approved_scenes(project_id: str) -> list[dict]:
    """Load all scenes for this project from DB, ordered by scene_number."""
    from ...database import AsyncSessionLocal
    from ...models.scene import Scene
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Scene)
            .where(Scene.project_id == uuid.UUID(project_id))
            .order_by(Scene.scene_number)
        )
        scenes = result.scalars().all()

    return [
        {
            "id": str(s.id),
            "scene_number": s.scene_number,
            "title": s.title or f"Scene {s.scene_number}",
            "description": s.description or "",
            "video_prompt": s.video_prompt or "",
            "duration_seconds": s.duration_seconds or 8,
            "characters_in_scene": s.characters_in_scene or [],
        }
        for s in scenes
    ]


# ── Shot Decomposition ───────────────────────────────────────────────────────

async def _decompose_scene(scene: dict, lookbook: dict, state: ProductionState) -> list[dict]:
    """
    Call Claude (chat_json) with CINEMATIC_DECOMPOSER_SYSTEM to decompose 1 scene.
    Returns list of shot dicts. Falls back to single shot if LLM fails.
    """
    user_prompt = cinematic_decomposer_user(
        scene_number=scene["scene_number"],
        scene_title=scene["title"],
        scene_description=scene["description"],
        scene_duration_seconds=scene["duration_seconds"],
        scene_video_prompt=scene["video_prompt"],
        characters_in_scene=scene["characters_in_scene"],
        lookbook=lookbook,
        genre=state.get("genre", "drama"),
        style=state.get("style", "cinematic"),
    )

    try:
        result = await chat_json(
            CINEMATIC_DECOMPOSER_SYSTEM,
            user_prompt,
            temperature=0.3,
            max_tokens=2048,
        )
        shots: list[dict] = result.get("shots", [])

        if not shots:
            return _fallback_shot(scene)

        # Keep APPROVED shots; if none, use highest-scoring
        approved = [s for s in shots if s.get("status") == "APPROVED"]
        if not approved:
            # Use highest-scoring shot even if REJECTED (don't fully discard Claude's work)
            approved = [max(shots, key=lambda x: float(x.get("qc_score", 0)))]

        # Cap duration at 8s for each shot
        for s in approved:
            s["duration"] = min(int(s.get("duration", 8)), 8)

        logger.info(
            "Scene %d decomposed into %d shots (%d approved by QC)",
            scene["scene_number"], len(shots), len(approved),
        )
        return approved

    except (LLMError, Exception) as e:
        logger.warning("Decomposer LLM failed for scene %d: %s — using fallback", scene["scene_number"], e)
        return _fallback_shot(scene)


def _fallback_shot(scene: dict) -> list[dict]:
    """Single shot using existing scene video_prompt (decomposer failure fallback)."""
    scene_num = scene["scene_number"]
    return [{
        "shot_id": f"SC{scene_num:02d}_SH01",
        "shot_number": 1,
        "duration": min(scene.get("duration_seconds", 8), 8),
        "prompt": scene["video_prompt"] or scene["description"] or f"Scene {scene_num}",
        "characters_present": scene.get("characters_in_scene") or [],
        "qc_score": 7.0,
        "qc_notes": "Fallback — decomposer LLM failed; using scene video_prompt",
        "status": "APPROVED",
    }]


# ── DB Persistence ───────────────────────────────────────────────────────────

async def _clear_shots(project_id: str) -> None:
    """Delete all existing shots for this project before regenerating."""
    from ...database import AsyncSessionLocal
    from ...models.shot import Shot
    from sqlalchemy import delete

    async with AsyncSessionLocal() as db:
        await db.execute(delete(Shot).where(Shot.project_id == uuid.UUID(project_id)))
        await db.commit()


async def _save_shots(scene_id: str, project_id: str, shot_dicts: list[dict]) -> list[dict]:
    """
    Save shot dicts to DB and return saved dicts with DB ids.
    """
    from ...database import AsyncSessionLocal
    from ...models.shot import Shot

    saved: list[dict] = []
    async with AsyncSessionLocal() as db:
        for s in shot_dicts:
            shot = Shot(
                scene_id=uuid.UUID(scene_id),
                project_id=uuid.UUID(project_id),
                shot_id=s.get("shot_id", ""),
                shot_number=int(s.get("shot_number", 1)),
                duration=int(s.get("duration", 8)),
                prompt=s.get("prompt", ""),
                characters_present=s.get("characters_present") or [],
                qc_score=float(s.get("qc_score", 7.0)) if s.get("qc_score") is not None else None,
                qc_notes=s.get("qc_notes", ""),
                status=s.get("status", "APPROVED"),
            )
            db.add(shot)
            saved.append({
                "shot_id": shot.shot_id,
                "shot_number": shot.shot_number,
                "duration": shot.duration,
                "prompt": shot.prompt,
                "characters_present": shot.characters_present,
                "qc_score": shot.qc_score,
                "qc_notes": shot.qc_notes,
                "status": shot.status,
                "scene_id": scene_id,
            })
        await db.commit()

    return saved
