"""Celery tasks for AI character image generation."""
import asyncio
import logging
import uuid
from typing import Optional

from .celery_app import celery_app

logger = logging.getLogger(__name__)


def _run(coro):
    """Run an async coroutine from a Celery task (sync context)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    name="character_tasks.generate_character_variants",
    queue="cpu_queue",
    acks_late=True,
    max_retries=2,
    default_retry_delay=10,
)
def generate_character_variants(
    self,
    project_id: str,
    description: str,
    name: str = "",
    ref_r2_key: Optional[str] = None,
):
    """
    Generate 3 character variant images (variant_index 0, 1, 2).
    Publishes SSE events as each variant completes.
    Saves Character rows to the database.
    """
    return _run(_generate_variants_async(self, project_id, description, name, ref_r2_key))


async def _generate_variants_async(task, project_id: str, description: str, name: str, ref_r2_key: Optional[str]):
    from ..database import AsyncSessionLocal
    from ..models.character import Character, CharacterSource
    from ..models.generation_task import GenerationTask, TaskType, TaskStatus
    from ..services.image_fallback_service import generate_image, ImageGenError
    from ..services.r2_service import upload_bytes, download_bytes
    from ..services.sse_service import publish_event

    logger.info("Starting character generation for project %s", project_id)

    # Download reference image if provided
    ref_bytes: bytes | None = None
    if ref_r2_key:
        try:
            ref_bytes = await download_bytes(ref_r2_key)
        except Exception as e:
            logger.warning("Failed to download ref image %s: %s", ref_r2_key, e)

    # Build generation prompt
    source = CharacterSource.user_upload if ref_r2_key else CharacterSource.ai_generated
    prompt_base = _build_character_prompt(description, name)

    results = []
    for variant_index in range(3):
        await publish_event(project_id, {
            "type": "character_progress",
            "variant_index": variant_index,
            "status": "generating",
            "message": f"Đang tạo biến thể {variant_index + 1}/3...",
        })

        try:
            image_bytes, provider = await generate_image(
                prompt=_variant_prompt(prompt_base, variant_index),
                variant_index=variant_index,
                ref_image_bytes=ref_bytes,
            )

            # Upload to R2
            r2_key = f"projects/{project_id}/characters/variant_{variant_index}.png"
            await upload_bytes(r2_key, image_bytes, content_type="image/png")

            # Save character to DB
            async with AsyncSessionLocal() as db:
                # Remove existing variant if regenerating
                from sqlalchemy import select, delete
                from ..models.character import Character as CharModel
                await db.execute(
                    delete(CharModel).where(
                        CharModel.project_id == uuid.UUID(project_id),
                        CharModel.variant_index == variant_index,
                    )
                )
                char = CharModel(
                    project_id=uuid.UUID(project_id),
                    name=name or f"Nhân vật {variant_index + 1}",
                    description=description,
                    variant_index=variant_index,
                    image_r2_key=r2_key,
                    is_selected=False,
                    source=source,
                    user_ref_r2_key=ref_r2_key,
                )
                db.add(char)
                await db.commit()
                await db.refresh(char)
                char_id = str(char.id)

            results.append({"variant_index": variant_index, "character_id": char_id, "r2_key": r2_key})

            await publish_event(project_id, {
                "type": "character_ready",
                "variant_index": variant_index,
                "character_id": char_id,
                "r2_key": r2_key,
                "provider": provider,
            })
            logger.info("Character variant %d ready (provider: %s)", variant_index, provider)

        except (ImageGenError, Exception) as exc:
            logger.error("Character variant %d failed: %s", variant_index, exc)
            await publish_event(project_id, {
                "type": "character_error",
                "variant_index": variant_index,
                "error": str(exc),
            })

    await publish_event(project_id, {
        "type": "character_done",
        "results": results,
        "total": len(results),
    })
    return results


def _build_character_prompt(description: str, name: str) -> str:
    base = f"portrait of a character"
    if name:
        base += f" named {name}"
    if description:
        base += f", {description}"
    base += ", high quality, detailed face, professional lighting, clean background"
    return base


def _variant_prompt(base: str, variant_index: int) -> str:
    styles = [
        "professional office attire, formal, confident",
        "casual young style, energetic, modern streetwear",
        "warm friendly smile, approachable, natural lighting",
    ]
    return f"{base}, {styles[variant_index]}"
