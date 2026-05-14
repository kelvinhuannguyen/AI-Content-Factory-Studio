"""Shots API — list and edit cinematic shots from the Cinematic Scene Decomposer."""
import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ...database import get_db
from ...models.shot import Shot

router = APIRouter()
logger = logging.getLogger(__name__)


def _shot_to_dict(s: Shot) -> dict:
    return {
        "id": str(s.id),
        "scene_id": str(s.scene_id),
        "project_id": str(s.project_id),
        "shot_id": s.shot_id,
        "shot_number": s.shot_number,
        "duration": s.duration,
        "prompt": s.prompt,
        "characters_present": s.characters_present or [],
        "qc_score": s.qc_score,
        "qc_notes": s.qc_notes,
        "status": s.status,
        "clip_r2_key": s.clip_r2_key,
        "created_at": s.created_at.isoformat(),
    }


@router.get("/{project_id}")
async def get_shots(project_id: str, db: AsyncSession = Depends(get_db)):
    """List all approved shots for a project, ordered by scene then shot number."""
    try:
        pid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(422, "Invalid project_id")

    result = await db.execute(
        select(Shot)
        .where(Shot.project_id == pid)
        .order_by(Shot.scene_id, Shot.shot_number)
    )
    return [_shot_to_dict(s) for s in result.scalars().all()]


@router.patch("/{shot_id}")
async def update_shot(shot_id: str, body: dict, db: AsyncSession = Depends(get_db)):
    """
    Edit a shot's prompt or duration before video generation.
    Allowed fields: prompt, duration, characters_present.
    """
    try:
        sid = uuid.UUID(shot_id)
    except ValueError:
        raise HTTPException(422, "Invalid shot_id")

    shot = await db.get(Shot, sid)
    if not shot:
        raise HTTPException(404, "Shot not found")

    allowed = {"prompt", "duration", "characters_present"}
    for key, val in body.items():
        if key in allowed and val is not None:
            if key == "duration":
                val = min(int(val), 8)  # enforce 8s cap
            setattr(shot, key, val)

    await db.commit()
    await db.refresh(shot)
    return _shot_to_dict(shot)
