"""SEO Package API — generate, get, patch, trigger thumbnail."""
import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from ...database import get_db
from ...models.project import Project, ProjectStatus
from ...models.seo_package import SeoPackage
from ...models.script import Script
from ...services.llm_service import chat_json, LLMError
from ...services.image_fallback_service import generate_image
from ...services.r2_service import upload_bytes, public_url, generate_presigned_url
from ...utils.prompt_templates import SEO_SYSTEM, seo_user

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/generate", status_code=201)
async def generate_seo(body: dict, db: AsyncSession = Depends(get_db)):
    """
    GPT (gemini-2.5-flash) tạo gói SEO đầy đủ:
    5 tiêu đề · mô tả dài · 50 tags · thumbnail prompt.
    Lưu vào seo_packages, cập nhật project.status → seo_ready.
    Body: { project_id }
    """
    project_id = body.get("project_id")
    if not project_id:
        raise HTTPException(422, "project_id required")
    try:
        pid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(422, "Invalid project_id")

    proj = await db.get(Project, pid)
    if not proj:
        raise HTTPException(404, "Project not found")

    # Lấy script để có context
    script_result = await db.execute(
        select(Script).where(Script.project_id == pid).order_by(Script.version.desc())
    )
    script = script_result.scalars().first()
    script_summary = (script.content_raw or "")[:500] if script else ""

    user_prompt = seo_user(
        topic=proj.topic or "",
        genre=proj.genre or "",
        script_summary=script_summary,
        language=proj.preferred_language or "vi",
    )

    try:
        result = await chat_json(SEO_SYSTEM, user_prompt, temperature=0.7, max_tokens=3000)
    except LLMError as e:
        raise HTTPException(502, f"AI error: {e}")

    # Xóa gói SEO cũ nếu có (regenerate)
    await db.execute(delete(SeoPackage).where(SeoPackage.project_id == pid))

    seo = SeoPackage(
        project_id=pid,
        title_variants=result.get("title_variants", []),
        description=result.get("description", ""),
        tags=result.get("tags", []),
        thumbnail_prompt=result.get("thumbnail_prompt", ""),
    )
    db.add(seo)
    proj.status = ProjectStatus.seo_ready
    await db.commit()
    await db.refresh(seo)

    return _seo_to_dict(seo)


@router.post("/{project_id}/thumbnail", status_code=202)
async def generate_thumbnail(project_id: str, db: AsyncSession = Depends(get_db)):
    """
    Tạo thumbnail bằng flux-1.1-ultra (async trong background).
    Dùng thumbnail_prompt đã có từ SEO package.
    """
    try:
        pid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(422, "Invalid project_id")

    result = await db.execute(
        select(SeoPackage).where(SeoPackage.project_id == pid).order_by(SeoPackage.created_at.desc())
    )
    seo = result.scalars().first()
    if not seo:
        raise HTTPException(404, "Chưa có SEO package. Gọi /generate trước.")

    prompt = seo.thumbnail_prompt or f"YouTube thumbnail for: {seo.title_variants[0] if seo.title_variants else 'video'}"

    try:
        img_bytes, provider = await generate_image(prompt, variant_index=0)
        r2_key = f"projects/{project_id}/thumbnail.png"
        await upload_bytes(r2_key, img_bytes, content_type="image/png")

        seo.thumbnail_r2_key = r2_key
        await db.commit()
        await db.refresh(seo)

        thumb_url = public_url(r2_key) or await generate_presigned_url(r2_key)
        return {
            "status": "done",
            "thumbnail_r2_key": r2_key,
            "thumbnail_url": thumb_url,
            "provider": provider,
        }
    except Exception as e:
        logger.error("Thumbnail gen failed: %s", e)
        raise HTTPException(502, f"Thumbnail generation failed: {e}")


@router.get("/{project_id}")
async def get_seo(project_id: str, db: AsyncSession = Depends(get_db)):
    try:
        pid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(422, "Invalid project_id")

    result = await db.execute(
        select(SeoPackage).where(SeoPackage.project_id == pid).order_by(SeoPackage.created_at.desc())
    )
    seo = result.scalars().first()
    if not seo:
        raise HTTPException(404, "SEO package not found")
    return _seo_to_dict(seo)


@router.patch("/{project_id}")
async def update_seo(project_id: str, body: dict, db: AsyncSession = Depends(get_db)):
    """User edits: selected_title_index, description, tags."""
    try:
        pid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(422, "Invalid project_id")

    result = await db.execute(
        select(SeoPackage).where(SeoPackage.project_id == pid).order_by(SeoPackage.created_at.desc())
    )
    seo = result.scalars().first()
    if not seo:
        raise HTTPException(404, "SEO package not found")

    if "description" in body:
        seo.description = body["description"]
    if "tags" in body and isinstance(body["tags"], list):
        seo.tags = body["tags"]
    # Allow swapping title to front of list
    if "selected_title_index" in body:
        idx = int(body["selected_title_index"])
        if seo.title_variants and 0 <= idx < len(seo.title_variants):
            titles = list(seo.title_variants)
            chosen = titles.pop(idx)
            titles.insert(0, chosen)
            seo.title_variants = titles

    await db.commit()
    await db.refresh(seo)
    return _seo_to_dict(seo)


def _seo_to_dict(seo: SeoPackage) -> dict:
    thumb_url = None
    if seo.thumbnail_r2_key:
        thumb_url = public_url(seo.thumbnail_r2_key)
    return {
        "id": str(seo.id),
        "project_id": str(seo.project_id),
        "title_variants": seo.title_variants or [],
        "description": seo.description or "",
        "tags": seo.tags or [],
        "thumbnail_r2_key": seo.thumbnail_r2_key,
        "thumbnail_url": thumb_url,
        "thumbnail_prompt": seo.thumbnail_prompt,
        "youtube_video_id": seo.youtube_video_id,
        "published_at": seo.published_at.isoformat() if seo.published_at else None,
        "created_at": seo.created_at.isoformat(),
    }
