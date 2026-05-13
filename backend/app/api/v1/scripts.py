import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ...database import get_db
from ...models import Script, Project, ProjectStatus
from ...services.llm_service import chat_json, LLMError
from ...utils.prompt_templates import SCRIPT_SYSTEM, script_user

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/generate")
async def generate_script(body: dict, db: AsyncSession = Depends(get_db)):
    """
    Generate a Hollywood-standard script via GPT-4o.
    Body: { project_id, topic, genre, style, duration_seconds, production_type, language?, additional_notes? }
    """
    project_id      = body.get("project_id")
    topic           = body.get("topic", "")
    genre           = body.get("genre", "educational")
    style           = body.get("style", "cinematic")
    duration_seconds = int(body.get("duration_seconds", 60))
    production_type = body.get("production_type", "short_video")
    language        = body.get("language", "vi")
    additional_notes = body.get("additional_notes", "")

    if not topic:
        raise HTTPException(status_code=422, detail="topic is required")

    # Build prompt and call GPT-4o
    try:
        user_prompt = script_user(
            topic=topic,
            genre=genre,
            style=style,
            duration_seconds=duration_seconds,
            production_type=production_type,
            language=language,
            additional_notes=additional_notes,
        )
        result = await chat_json(SCRIPT_SYSTEM, user_prompt, temperature=0.8, max_tokens=6000)
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"AI service error: {e}")

    # Compute word count
    full_text: str = result.get("full_script_text", "")
    word_count = len(full_text.split())

    # Convert to HTML for Tiptap editor
    content_html = _script_to_html(result)

    # Save to DB if project_id provided
    script_id = None
    if project_id:
        try:
            pid = uuid.UUID(project_id)
            # Increment version
            existing = await db.execute(
                select(Script).where(Script.project_id == pid).order_by(Script.version.desc())
            )
            latest = existing.scalars().first()
            version = (latest.version + 1) if latest else 1

            script = Script(
                project_id=pid,
                version=version,
                content_raw=full_text,
                content_html=content_html,
                word_count=word_count,
                estimated_duration_seconds=result.get("total_estimated_seconds", duration_seconds),
            )
            db.add(script)

            # Update project status
            proj = await db.get(Project, pid)
            if proj:
                proj.status = ProjectStatus.script_ready
                proj.topic = topic

            await db.commit()
            await db.refresh(script)
            script_id = str(script.id)
        except Exception as e:
            logger.error("DB save error: %s", e)
            await db.rollback()

    return {
        "script_id": script_id,
        "title": result.get("title", topic),
        "hook": result.get("hook", ""),
        "scenes": result.get("scenes", []),
        "full_script_text": full_text,
        "content_html": content_html,
        "word_count": word_count,
        "estimated_duration_seconds": result.get("total_estimated_seconds", duration_seconds),
    }


@router.get("/{project_id}")
async def get_script(project_id: str, db: AsyncSession = Depends(get_db)):
    try:
        pid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid project_id")

    result = await db.execute(
        select(Script).where(Script.project_id == pid).order_by(Script.version.desc())
    )
    script = result.scalars().first()
    if not script:
        raise HTTPException(status_code=404, detail="No script found for this project")

    return _script_to_dict(script)


@router.put("/{script_id}")
async def update_script(script_id: str, body: dict, db: AsyncSession = Depends(get_db)):
    try:
        sid = uuid.UUID(script_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid script_id")

    script = await db.get(Script, sid)
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")

    if "content_html" in body:
        script.content_html = body["content_html"]
        # Recompute word count from HTML (strip tags)
        import re
        text = re.sub(r"<[^>]+>", " ", body["content_html"])
        script.word_count = len(text.split())

    await db.commit()
    await db.refresh(script)
    return _script_to_dict(script)


@router.post("/{script_id}/approve")
async def approve_script(script_id: str, db: AsyncSession = Depends(get_db)):
    try:
        sid = uuid.UUID(script_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid script_id")

    script = await db.get(Script, sid)
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")

    script.approved = True

    # Advance project status
    proj = await db.get(Project, script.project_id)
    if proj and proj.status == ProjectStatus.script_ready:
        proj.status = ProjectStatus.config_done

    await db.commit()
    return {"approved": True, "script_id": script_id}


@router.post("/{script_id}/regenerate")
async def regenerate_script(script_id: str, body: dict, db: AsyncSession = Depends(get_db)):
    """Reset approval and generate a new version."""
    try:
        sid = uuid.UUID(script_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid script_id")

    script = await db.get(Script, sid)
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")

    # Get project info for re-generation
    proj = await db.get(Project, script.project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    return await generate_script(
        {
            "project_id": str(proj.id),
            "topic": proj.topic or body.get("topic", ""),
            "genre": proj.genre or body.get("genre", "educational"),
            "style": proj.style or body.get("style", "cinematic"),
            "duration_seconds": proj.duration_seconds or 60,
            "production_type": proj.production_type,
            "language": proj.preferred_language,
        },
        db=db,
    )


def _script_to_dict(s: Script) -> dict:
    return {
        "id": str(s.id),
        "project_id": str(s.project_id),
        "version": s.version,
        "content_raw": s.content_raw,
        "content_html": s.content_html,
        "word_count": s.word_count,
        "estimated_duration_seconds": s.estimated_duration_seconds,
        "approved": s.approved,
        "created_at": s.created_at.isoformat(),
    }


def _script_to_html(result: dict) -> str:
    """Convert GPT-4o script JSON to simple HTML for Tiptap."""
    parts = []
    if result.get("title"):
        parts.append(f"<h2>{result['title']}</h2>")
    if result.get("hook"):
        parts.append(f"<p><strong>[HOOK]</strong> {result['hook']}</p>")
    for scene in result.get("scenes", []):
        parts.append(
            f"<h3>Cảnh {scene.get('scene_number', '?')}: {scene.get('title', '')} "
            f"({scene.get('duration_seconds', 0)}s)</h3>"
        )
        if scene.get("narration"):
            parts.append(f"<p><em>{scene['narration']}</em></p>")
        if scene.get("shot_description"):
            parts.append(f"<p><strong>[Cảnh quay]</strong> {scene['shot_description']}</p>")
        if scene.get("on_screen_text"):
            parts.append(f"<p><strong>[Chữ màn hình]</strong> {scene['on_screen_text']}</p>")
    return "".join(parts) or f"<p>{result.get('full_script_text', '')}</p>"
