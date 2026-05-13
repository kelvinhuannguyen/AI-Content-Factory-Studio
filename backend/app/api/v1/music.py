from fastapi import APIRouter

router = APIRouter()


@router.post("/generate")
async def generate_music(body: dict):
    return {"status": "not_implemented", "message": "Phase 2: Suno AI music generation"}


@router.get("/{project_id}")
async def get_music_tracks(project_id: str):
    return {"status": "not_implemented"}


@router.post("/{track_id}/select")
async def select_track(track_id: str):
    return {"status": "not_implemented"}
