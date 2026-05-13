"""Publish API — YouTube upload + download link."""
import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ...database import get_db
from ...models.project import Project, ProjectStatus
from ...models.seo_package import SeoPackage
from ...services.r2_service import download_bytes, generate_presigned_url
from ...services.youtube_service import upload_video, get_video_url, YouTubeError

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/youtube")
async def publish_to_youtube(body: dict, db: AsyncSession = Depends(get_db)):
    """
    Upload final video to YouTube using SEO package metadata.
    Body: {
        project_id: str,
        privacy: "public" | "unlisted" | "private",   default: "unlisted"
        credentials_json?: str   # OAuth2 token JSON
    }
    """
    project_id = body.get("project_id")
    if not project_id:
        raise HTTPException(422, "project_id required")
    try:
        pid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(422, "Invalid project_id")

    privacy = body.get("privacy", "unlisted")
    credentials_json = body.get("credentials_json")

    proj = await db.get(Project, pid)
    if not proj:
        raise HTTPException(404, "Project not found")
    if not proj.final_video_r2_key:
        raise HTTPException(422, "Chưa có video final. Chạy pipeline tạo video trước.")

    # Lấy SEO package
    seo_result = await db.execute(
        select(SeoPackage).where(SeoPackage.project_id == pid).order_by(SeoPackage.created_at.desc())
    )
    seo = seo_result.scalars().first()
    if not seo:
        raise HTTPException(422, "Chưa có SEO package. Gọi /seo/generate trước.")

    title = (seo.title_variants or ["Video"])[0]
    description = seo.description or ""
    tags = seo.tags or []

    # Download video from R2
    try:
        video_bytes = await download_bytes(proj.final_video_r2_key)
    except Exception as e:
        raise HTTPException(502, f"Không thể tải video từ R2: {e}")

    # Upload to YouTube
    try:
        video_id = await upload_video(
            video_bytes=video_bytes,
            title=title,
            description=description,
            tags=tags,
            privacy=privacy,
            credentials_json=credentials_json,
        )
    except YouTubeError as e:
        raise HTTPException(502, str(e))

    # Save youtube_video_id + published_at
    seo.youtube_video_id = video_id
    seo.published_at = datetime.now(timezone.utc)
    proj.status = ProjectStatus.published
    await db.commit()

    youtube_url = await get_video_url(video_id)
    return {
        "status": "published",
        "youtube_video_id": video_id,
        "youtube_url": youtube_url,
        "privacy": privacy,
        "title": title,
    }


@router.get("/{project_id}/status")
async def get_publish_status(project_id: str, db: AsyncSession = Depends(get_db)):
    """Return project publish status + YouTube URL if available."""
    try:
        pid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(422, "Invalid project_id")

    proj = await db.get(Project, pid)
    if not proj:
        raise HTTPException(404, "Project not found")

    seo_result = await db.execute(
        select(SeoPackage).where(SeoPackage.project_id == pid).order_by(SeoPackage.created_at.desc())
    )
    seo = seo_result.scalars().first()

    return {
        "project_status": proj.status,
        "final_video_r2_key": proj.final_video_r2_key,
        "youtube_video_id": seo.youtube_video_id if seo else None,
        "youtube_url": f"https://www.youtube.com/watch?v={seo.youtube_video_id}" if seo and seo.youtube_video_id else None,
        "published_at": seo.published_at.isoformat() if seo and seo.published_at else None,
    }


@router.get("/{project_id}/download")
async def get_download_url(project_id: str, db: AsyncSession = Depends(get_db)):
    """Generate a presigned 1-hour download URL for the final MP4."""
    try:
        pid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(422, "Invalid project_id")

    proj = await db.get(Project, pid)
    if not proj or not proj.final_video_r2_key:
        raise HTTPException(404, "Video final không tồn tại")

    try:
        url = await generate_presigned_url(proj.final_video_r2_key, expires=3600)
    except Exception as e:
        raise HTTPException(502, f"Không thể tạo download URL: {e}")

    return {
        "download_url": url,
        "expires_in": 3600,
        "filename": f"final_{project_id[:8]}.mp4",
    }
