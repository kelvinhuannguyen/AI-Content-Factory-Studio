"""Scenes API — generate scene breakdown from script, CRUD, update prompts."""
import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from ...database import get_db
from ...models.scene import Scene, SceneStatus
from ...models.project import Project, ProjectStatus
from ...models.script import Script
from ...services.llm_service import chat_json, LLMError
from ...services.sse_service import publish_event
from ...utils.prompt_templates import SCENE_PROMPT_SYSTEM, scene_prompt_user

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/generate", status_code=201)
async def generate_scenes(body: dict, db: AsyncSession = Depends(get_db)):
    """
    GPT-4o: kịch bản → danh sách cảnh với video prompt cho từng cảnh.
    Body: { project_id, character_description? }
    """
    project_id = body.get("project_id")
    if not project_id:
        raise HTTPException(422, "project_id is required")

    try:
        pid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(422, "Invalid project_id")

    project = await db.get(Project, pid)
    if not project:
        raise HTTPException(404, "Project not found")

    # Lấy kịch bản mới nhất
    result = await db.execute(
        select(Script).where(Script.project_id == pid).order_by(Script.version.desc())
    )
    script = result.scalars().first()
    if not script or not script.content_raw:
        raise HTTPException(422, "Cần viết kịch bản trước khi phân cảnh")

    character_description = body.get("character_description", "")

    await publish_event(project_id, {
        "type": "agent_start",
        "agent": "scene_planner",
        "message": "Đang phân tích kịch bản thành cảnh quay...",
    })

    # GPT-4o phân cảnh
    try:
        scene_data = await _generate_scene_prompts(
            script=script,
            project=project,
            character_description=character_description,
        )
    except LLMError as e:
        raise HTTPException(502, f"AI error: {e}")

    # Xóa scenes cũ nếu có (regenerate)
    await db.execute(delete(Scene).where(Scene.project_id == pid))

    # Lưu scenes mới vào DB
    scenes_out = []
    for i, s in enumerate(scene_data):
        scene = Scene(
            project_id=pid,
            scene_number=i + 1,
            title=s.get("title", f"Cảnh {i + 1}"),
            description=s.get("description", ""),
            video_prompt=s.get("video_prompt", ""),
            duration_seconds=s.get("duration_seconds", 10),
            status=SceneStatus.pending,
        )
        db.add(scene)
        scenes_out.append(scene)

    # Cập nhật project status
    project.status = ProjectStatus.scenes_ready
    await db.commit()
    for s in scenes_out:
        await db.refresh(s)

    await publish_event(project_id, {
        "type": "agent_done",
        "agent": "scene_planner",
        "scene_count": len(scenes_out),
        "message": f"Đã phân {len(scenes_out)} cảnh. Kiểm tra và chỉnh sửa prompt trước khi tạo video.",
    })

    return [_scene_to_dict(s) for s in scenes_out]


@router.get("/{project_id}")
async def get_scenes(project_id: str, db: AsyncSession = Depends(get_db)):
    try:
        pid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(422, "Invalid project_id")

    result = await db.execute(
        select(Scene).where(Scene.project_id == pid).order_by(Scene.scene_number)
    )
    return [_scene_to_dict(s) for s in result.scalars().all()]


@router.patch("/{scene_id}")
async def update_scene(scene_id: str, body: dict, db: AsyncSession = Depends(get_db)):
    """Cập nhật video_prompt hoặc duration của một cảnh."""
    try:
        sid = uuid.UUID(scene_id)
    except ValueError:
        raise HTTPException(422, "Invalid scene_id")

    scene = await db.get(Scene, sid)
    if not scene:
        raise HTTPException(404, "Scene not found")

    allowed = {"title", "description", "video_prompt", "duration_seconds"}
    for key, val in body.items():
        if key in allowed and val is not None:
            setattr(scene, key, val)

    await db.commit()
    await db.refresh(scene)
    return _scene_to_dict(scene)


@router.post("/{scene_id}/regenerate-prompt")
async def regenerate_scene_prompt(scene_id: str, body: dict, db: AsyncSession = Depends(get_db)):
    """Tạo lại video prompt cho một cảnh đơn lẻ."""
    try:
        sid = uuid.UUID(scene_id)
    except ValueError:
        raise HTTPException(422, "Invalid scene_id")

    scene = await db.get(Scene, sid)
    if not scene:
        raise HTTPException(404, "Scene not found")

    project = await db.get(Project, scene.project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    try:
        user_prompt = scene_prompt_user(
            scene_title=scene.title or "",
            shot_description=scene.description or "",
            narration="",
            character_description=body.get("character_description", ""),
            genre=project.genre or "",
            style=project.style or "",
            production_type=str(project.production_type),
        )
        result = await chat_json(SCENE_PROMPT_SYSTEM, user_prompt, temperature=0.7, max_tokens=500)
        scene.video_prompt = result.get("video_prompt", scene.video_prompt)
    except LLMError as e:
        raise HTTPException(502, f"AI error: {e}")

    await db.commit()
    await db.refresh(scene)
    return _scene_to_dict(scene)


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _generate_scene_prompts(script: Script, project: Project, character_description: str) -> list[dict]:
    """
    Parse existing scenes from script JSON + enrich each with a video_prompt via GPT-4o.
    Falls back to description-based prompts if scene breakdown is not in content_raw.
    """
    import json, re

    # Try to extract scenes from content_raw (GPT script JSON embedded as JSON block)
    parsed_scenes: list[dict] = []
    try:
        raw = script.content_raw or ""
        # Script JSON may be stored directly or inside content_raw
        data = json.loads(raw)
        parsed_scenes = data.get("scenes", [])
    except (json.JSONDecodeError, TypeError):
        pass

    if not parsed_scenes:
        # Fallback: ask GPT to break down content_raw into scenes
        from ...services.llm_service import chat_json as _chat_json
        fallback_result = await _chat_json(
            "Bạn là biên kịch phân tích kịch bản thành các cảnh quay. Trả về JSON.",
            f"""Phân tích kịch bản sau thành 4-8 cảnh quay, mỗi cảnh có tiêu đề, mô tả, thời lượng (giây):

{(script.content_raw or "")[:3000]}

Trả về JSON:
{{"scenes": [{{"scene_number":1,"title":"...","description":"...","duration_seconds":10}}]}}""",
            temperature=0.6,
            max_tokens=2000,
        )
        parsed_scenes = fallback_result.get("scenes", [])

    # Enrich each scene with video_prompt via GPT-4o
    enriched = []
    for s in parsed_scenes:
        try:
            user_prompt = scene_prompt_user(
                scene_title=s.get("title", ""),
                shot_description=s.get("shot_description") or s.get("description", ""),
                narration=s.get("narration", ""),
                character_description=character_description,
                genre=project.genre or "",
                style=project.style or "",
                production_type=str(project.production_type),
            )
            result = await chat_json(SCENE_PROMPT_SYSTEM, user_prompt, temperature=0.7, max_tokens=500)
            enriched.append({
                "title": s.get("title", f"Cảnh {len(enriched)+1}"),
                "description": s.get("shot_description") or s.get("description", ""),
                "video_prompt": result.get("video_prompt", ""),
                "duration_seconds": int(s.get("duration_seconds", 10)),
            })
        except Exception as e:
            logger.warning("Scene prompt gen failed for scene %s: %s", s.get("title"), e)
            enriched.append({
                "title": s.get("title", f"Cảnh {len(enriched)+1}"),
                "description": s.get("description", ""),
                "video_prompt": s.get("shot_description", ""),
                "duration_seconds": int(s.get("duration_seconds", 10)),
            })

    return enriched


def _scene_to_dict(s: Scene) -> dict:
    return {
        "id": str(s.id),
        "project_id": str(s.project_id),
        "scene_number": s.scene_number,
        "title": s.title,
        "description": s.description,
        "video_prompt": s.video_prompt,
        "duration_seconds": s.duration_seconds,
        "status": s.status,
        "clip_r2_key": s.clip_r2_key,
        "thumbnail_r2_key": s.thumbnail_r2_key,
        "created_at": s.created_at.isoformat(),
    }
