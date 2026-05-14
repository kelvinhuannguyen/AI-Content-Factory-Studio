"""Character image generation — IP Character Production Pipeline.

New flow (replaces 3-variant system):
  _generate_character_image_async: generates 1 hero portrait per character profile
  _generate_character_sheet_async: generates character sheet (front+side, white bg) in background
"""
import asyncio
import logging
import uuid

from .celery_app import celery_app

logger = logging.getLogger(__name__)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Legacy Celery task (kept for backwards-compat API endpoint) ───────────

@celery_app.task(
    bind=True,
    name="character_tasks.generate_character_variants",
    queue="cpu_queue",
    acks_late=True,
    max_retries=2,
    default_retry_delay=10,
)
def generate_character_variants(self, project_id: str, description: str, name: str = "", ref_r2_key=None):
    """Legacy task — wraps new _generate_character_image_async with a fallback profile."""
    from ..langgraph.nodes.character_ip_pipeline import _build_fallback_profile
    profile = _build_fallback_profile(character_name=name, character_description=description)
    return _run(_generate_character_image_async(project_id, profile, ref_r2_key=ref_r2_key))


# ── Core async generation functions ──────────────────────────────────────

async def _generate_character_image_async(
    project_id: str,
    profile: dict,
    user_prompt_addition: str = "",
    ref_r2_key: str | None = None,
) -> str | None:
    """
    Chuẩn 1 + 2: Generate 1 hero portrait for 1 character using VIS-anchored prompt.
    - VIS as immutable prompt prefix (Chuẩn 1 — Character Reference)
    - Deterministic seed = character_index * 1337 + 42 (Chuẩn 2 — Fixed Seed)
    - Negative prompt blocks deviation from semantic invariants

    Saves Character row to DB with all IP fields.
    Publishes SSE: character_progress + character_ready.
    Returns: character DB UUID string, or None on failure.
    """
    from ..database import AsyncSessionLocal
    from ..models.character import Character, CharacterSource
    from ..services.image_fallback_service import generate_image, ImageGenError
    from ..services.r2_service import upload_bytes, download_bytes, public_url
    from ..services.sse_service import publish_event
    from ..langgraph.nodes.character_ip_pipeline import _build_image_prompt, _build_negative_prompt
    from sqlalchemy import delete

    ref_id = profile.get("ref_id", "#CHAR_01")
    char_index = profile.get("character_index", 0)
    name = profile.get("name", "")
    role = profile.get("role", "main")
    vis = profile.get("visual_identity_string", "")

    await publish_event(project_id, {
        "type": "character_progress",
        "character_index": char_index,
        "ref_id": ref_id,
        "name": name,
        "role": role,
        "message": f"Đang thiết kế {name or ref_id}...",
    })

    # Download reference image (user-uploaded) if provided
    ref_bytes: bytes | None = None
    if ref_r2_key:
        try:
            ref_bytes = await download_bytes(ref_r2_key)
        except Exception as e:
            logger.warning("Failed to download ref image %s: %s", ref_r2_key, e)

    prompt = _build_image_prompt(profile, user_prompt_addition=user_prompt_addition)
    negative = _build_negative_prompt(profile.get("physical_dna") or {})
    r2_key = f"projects/{project_id}/characters/{ref_id.lower().replace('#', '')}_hero.png"

    try:
        image_bytes, provider = await generate_image(
            prompt=prompt,
            negative_prompt=negative,
            variant_index=char_index,
            ref_image_bytes=ref_bytes,
        )
        await upload_bytes(r2_key, image_bytes, content_type="image/png")

        # Save Character row
        async with AsyncSessionLocal() as db:
            # Remove any existing row for this ref_id
            await db.execute(
                delete(Character).where(
                    Character.project_id == uuid.UUID(project_id),
                    Character.ref_id == ref_id,
                    Character.variant_index == 0,
                )
            )
            char = Character(
                project_id=uuid.UUID(project_id),
                name=name,
                description=vis,
                variant_index=0,
                image_r2_key=r2_key,
                is_selected=False,
                source=CharacterSource.ai_generated,
                user_ref_r2_key=ref_r2_key,
                character_index=char_index,
                ref_id=ref_id,
                visual_identity_string=vis,
                character_role=role,
                physical_dna=profile.get("physical_dna"),
                color_palette=profile.get("color_palette"),
                user_prompt_addition=user_prompt_addition or None,
            )
            db.add(char)
            await db.commit()
            await db.refresh(char)
            char_id = str(char.id)

        img_url = public_url(r2_key) or ""
        await publish_event(project_id, {
            "type": "character_ready",
            "character_index": char_index,
            "character_id": char_id,
            "ref_id": ref_id,
            "name": name,
            "role": role,
            "result_url": img_url,
            "provider": provider,
        })
        logger.info("Character %s (%s) ready — provider: %s", ref_id, name, provider)

        # Generate character sheet in background (non-fatal)
        asyncio.create_task(
            _generate_character_sheet_async(project_id, char_id, profile, image_bytes)
        )

        return char_id

    except Exception as exc:
        logger.error("Character %s generation failed: %s", ref_id, exc)
        await publish_event(project_id, {
            "type": "character_error",
            "character_index": char_index,
            "ref_id": ref_id,
            "error": str(exc),
        })
        return None


async def _generate_character_sheet_async(
    project_id: str,
    character_id: str,
    profile: dict,
    hero_image_bytes: bytes | None = None,
) -> None:
    """
    Chuẩn 1: Generate Character Sheet (front + side view, white background).
    Runs in background after hero portrait completes.
    Non-fatal — hero portrait is the primary deliverable.
    Updates Character.sheet_r2_key in DB when done.
    """
    from ..database import AsyncSessionLocal
    from ..models.character import Character
    from ..services.image_fallback_service import generate_image
    from ..services.r2_service import upload_bytes
    from ..langgraph.nodes.character_ip_pipeline import _build_sheet_prompt, _build_negative_prompt

    ref_id = profile.get("ref_id", "#CHAR_01")
    char_index = profile.get("character_index", 0)
    r2_key = f"projects/{project_id}/characters/{ref_id.lower().replace('#', '')}_sheet.png"

    try:
        prompt = _build_sheet_prompt(profile)
        negative = _build_negative_prompt(profile.get("physical_dna") or {})

        image_bytes, _ = await generate_image(
            prompt=prompt,
            negative_prompt=negative,
            variant_index=char_index + 10,  # different seed slot than hero
            ref_image_bytes=hero_image_bytes,
        )
        await upload_bytes(r2_key, image_bytes, content_type="image/png")

        async with AsyncSessionLocal() as db:
            char = await db.get(Character, uuid.UUID(character_id))
            if char:
                char.sheet_r2_key = r2_key
                await db.commit()

        logger.info("Character sheet for %s saved to R2: %s", ref_id, r2_key)

    except Exception as e:
        logger.warning("Character sheet generation for %s failed (non-fatal): %s", ref_id, e)


async def _load_characters(project_id: str) -> list[dict]:
    """Load all characters for a project from DB, sorted by character_index."""
    from ..database import AsyncSessionLocal
    from ..models.character import Character
    from ..services.r2_service import public_url
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

    return [
        {
            "id": str(c.id),
            "character_index": c.character_index,
            "ref_id": c.ref_id or f"#CHAR_0{c.character_index + 1}",
            "name": c.name,
            "role": c.character_role or ("main" if c.character_index == 0 else "supporting"),
            "variant_index": c.variant_index,
            "image_r2_key": c.image_r2_key,
            "image_url": public_url(c.image_r2_key) if c.image_r2_key else None,
            "sheet_r2_key": c.sheet_r2_key,
            "sheet_url": public_url(c.sheet_r2_key) if c.sheet_r2_key else None,
            "visual_identity_string": c.visual_identity_string,
            "physical_dna": c.physical_dna,
            "color_palette": c.color_palette,
            "user_prompt_addition": c.user_prompt_addition,
        }
        for c in chars
    ]
