import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from ...database import get_db
from ...models import Project, ProductionType, ProjectStatus

router = APIRouter()


@router.get("")
async def list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * page_size
    total_q = await db.execute(select(func.count(Project.id)))
    total = total_q.scalar_one()
    result = await db.execute(
        select(Project).order_by(Project.created_at.desc()).offset(offset).limit(page_size)
    )
    projects = result.scalars().all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_project_to_dict(p) for p in projects],
    }


@router.post("", status_code=201)
async def create_project(
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    project = Project(
        title=body.get("title", "Dự án mới"),
        production_type=ProductionType(body["production_type"]),
        preferred_language=body.get("preferred_language", "vi"),
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return _project_to_dict(project)


@router.get("/{project_id}")
async def get_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    project = await _get_or_404(project_id, db)
    return _project_to_dict(project)


@router.patch("/{project_id}")
async def update_project(project_id: uuid.UUID, body: dict, db: AsyncSession = Depends(get_db)):
    project = await _get_or_404(project_id, db)
    allowed = {"title", "status", "duration_seconds", "genre", "style", "topic", "preferred_language", "final_video_r2_key"}
    for key, val in body.items():
        if key in allowed and val is not None:
            if key == "status":
                val = ProjectStatus(val)
            setattr(project, key, val)
    await db.commit()
    await db.refresh(project)
    return _project_to_dict(project)


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    project = await _get_or_404(project_id, db)
    await db.delete(project)
    await db.commit()


@router.get("/{project_id}/status")
async def get_project_status(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    project = await _get_or_404(project_id, db)
    return {"id": str(project.id), "status": project.status, "updated_at": project.updated_at}


async def _get_or_404(project_id: uuid.UUID, db: AsyncSession) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _project_to_dict(p: Project) -> dict:
    return {
        "id": str(p.id),
        "title": p.title,
        "production_type": p.production_type,
        "status": p.status,
        "duration_seconds": p.duration_seconds,
        "genre": p.genre,
        "style": p.style,
        "topic": p.topic,
        "preferred_language": p.preferred_language,
        "final_video_r2_key": p.final_video_r2_key,
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
    }
