"""Characters API — generate, upload reference, list, select, customize, regenerate."""
import asyncio
import uuid
import logging
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from ...database import get_db
from ...models.character import Character, CharacterSource
from ...models.project import Project
from ...schemas.character import CharacterGenerateRequest, CharacterOut
from ...services.r2_service import upload_bytes, public_url, generate_presigned_url
from ...tasks.character_tasks import generate_character_variants

logger = logging.getLogger(__name__)
router = APIRouter()

_MAX_REF_SIZE = 10 * 1024 * 1024  # 10 MB


# ── Helpers ─────────────────────────────────────────────────────────────────

async def _get_project_or_404(project_id: uuid.UUID, db: AsyncSession) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    return project


async def _character_out(char: Character) -> CharacterOut:
    url = None
    if char.image_r2_key:
        url = public_url(char.image_r2_key)
        if url is None:
            try:
                url = await generate_presigned_url(char.image_r2_key, expires=3600)
            except Exception:
                pass
    sheet_url = public_url(char.sheet_r2_key) if char.sheet_r2_key else None
    return CharacterOut(
        id=char.id,
        project_id=char.project_id,
        name=char.name,
        description=char.description,
        variant_index=char.variant_index,
        image_r2_key=char.image_r2_key,
        image_url=url,
        is_selected=char.is_selected,
        source=char.source,
        user_ref_r2_key=char.user_ref_r2_key,
        character_index=char.character_index or 0,
        ref_id=char.ref_id,
        visual_identity_string=char.visual_identity_string,
        character_role=char.character_role,
        physical_dna=char.physical_dna,
        color_palette=char.color_palette,
        sheet_r2_key=char.sheet_r2_key,
        sheet_url=sheet_url,
        user_prompt_addition=char.user_prompt_addition,
    )


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/generate", status_code=202)
async def generate_characters(
    body: CharacterGenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Enqueue Celery task to generate 3 character variants. Events via SSE."""
    await _get_project_or_404(body.project_id, db)

    task = generate_character_variants.apply_async(
        kwargs={
            "project_id": str(body.project_id),
            "description": body.description,
            "name": body.name,
            "ref_r2_key": None,
        },
        queue="cpu_queue",
    )
    return {"status": "queued", "celery_task_id": task.id, "message": "Đang tạo 3 biến thể nhân vật..."}


@router.post("/upload-ref", status_code=202)
async def upload_reference_image(
    project_id: uuid.UUID = Form(...),
    name: str = Form(""),
    description: str = Form(""),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a user reference image then enqueue character generation."""
    await _get_project_or_404(project_id, db)

    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(400, f"Unsupported file type: {file.content_type}. Use JPEG, PNG, or WebP.")

    raw = await file.read()
    if len(raw) > _MAX_REF_SIZE:
        raise HTTPException(413, "File too large (max 10 MB)")

    # Upload reference to R2
    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}.get(file.content_type, "jpg")
    ref_key = f"projects/{project_id}/characters/user_ref.{ext}"
    await upload_bytes(ref_key, raw, content_type=file.content_type)

    task = generate_character_variants.apply_async(
        kwargs={
            "project_id": str(project_id),
            "description": description,
            "name": name,
            "ref_r2_key": ref_key,
        },
        queue="cpu_queue",
    )
    return {
        "status": "queued",
        "celery_task_id": task.id,
        "ref_r2_key": ref_key,
        "message": "Đang tạo 3 biến thể từ ảnh tham chiếu...",
    }


@router.get("/{project_id}")
async def get_characters(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """List all IP characters for a project (sorted by character_index)."""
    result = await db.execute(
        select(Character)
        .where(Character.project_id == project_id, Character.variant_index == 0)
        .order_by(Character.character_index)
    )
    chars = result.scalars().all()
    return [await _character_out(c) for c in chars]


@router.patch("/{character_id}/customize", status_code=200)
async def customize_character(
    character_id: uuid.UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """
    Save user's creative input for a character (without regenerating yet).
    Body: { user_prompt_addition?: str, vis_override?: str }
    """
    char = await db.get(Character, character_id)
    if not char:
        raise HTTPException(404, "Character not found")

    if "user_prompt_addition" in body:
        char.user_prompt_addition = body["user_prompt_addition"] or None
    if "vis_override" in body and body["vis_override"]:
        char.visual_identity_string = body["vis_override"]

    await db.commit()
    await db.refresh(char)
    return await _character_out(char)


@router.post("/{project_id}/regenerate/{ref_id}", status_code=202)
async def regenerate_single_character(
    project_id: uuid.UUID,
    ref_id: str,
    body: dict = {},
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Regenerate 1 specific character (by ref_id) with updated prompt.
    Runs generation in background. SSE will update the frontend when done.
    Body: { user_prompt_addition?: str, vis_override?: str }
    """
    await _get_project_or_404(project_id, db)

    # Find existing character row
    result = await db.execute(
        select(Character).where(
            Character.project_id == project_id,
            Character.ref_id == ref_id,
            Character.variant_index == 0,
        )
    )
    char = result.scalar_one_or_none()
    if not char:
        raise HTTPException(404, f"Character {ref_id} not found")

    # Rebuild profile from DB
    user_prompt_addition = body.get("user_prompt_addition") or char.user_prompt_addition or ""
    vis = body.get("vis_override") or char.visual_identity_string or char.description or ""

    profile = {
        "ref_id": char.ref_id or ref_id,
        "name": char.name or "",
        "role": char.character_role or "main",
        "character_index": char.character_index or 0,
        "visual_identity_string": vis,
        "physical_dna": char.physical_dna or {},
        "color_palette": char.color_palette or {},
    }

    # Update user_prompt_addition in DB immediately
    if "user_prompt_addition" in body:
        char.user_prompt_addition = body["user_prompt_addition"] or None
    if "vis_override" in body and body["vis_override"]:
        char.visual_identity_string = body["vis_override"]
        profile["visual_identity_string"] = body["vis_override"]
    await db.commit()

    # Delete old character rows for this ref_id before regenerating
    await db.execute(
        delete(Character).where(
            Character.project_id == project_id,
            Character.ref_id == ref_id,
        )
    )
    await db.commit()

    # Run generation in background
    from ...tasks.character_tasks import _generate_character_image_async
    pid_str = str(project_id)

    async def _regen():
        await _generate_character_image_async(
            pid_str,
            profile,
            user_prompt_addition=user_prompt_addition,
            ref_r2_key=char.user_ref_r2_key,
        )

    if background_tasks:
        background_tasks.add_task(_regen)
    else:
        asyncio.create_task(_regen())

    return {"status": "generating", "ref_id": ref_id, "message": f"Đang tạo lại {ref_id}..."}


@router.post("/{character_id}/select", status_code=200)
async def select_character(character_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Mark a character as selected, unselect all siblings."""
    result = await db.execute(select(Character).where(Character.id == character_id))
    char = result.scalar_one_or_none()
    if not char:
        raise HTTPException(404, "Character not found")

    # Unselect siblings
    siblings = await db.execute(
        select(Character).where(Character.project_id == char.project_id)
    )
    for sibling in siblings.scalars().all():
        sibling.is_selected = sibling.id == character_id

    await db.commit()
    await db.refresh(char)
    return await _character_out(char)


@router.delete("/{project_id}/all", status_code=204)
async def delete_all_characters(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Delete all characters for a project (to allow regeneration)."""
    await db.execute(delete(Character).where(Character.project_id == project_id))
    await db.commit()
