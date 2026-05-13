"""Quality scoring service — extract keyframes from final video + GPT-5.4 Vision."""
from __future__ import annotations
import logging
import tempfile
from pathlib import Path

from .llm_service import chat_vision, LLMError
from .r2_service import download_bytes
from .ffmpeg_service import extract_keyframe
from ..utils.prompt_templates import QUALITY_SYSTEM, QUALITY_USER_TEMPLATE

logger = logging.getLogger(__name__)

# Max frames to send — vision models charge per image token
_MAX_FRAMES = 5
_FRAME_OFFSETS = [1.0, 5.0, 15.0, 30.0, 50.0]   # seconds into the video


async def score_video(
    project_id: str,
    final_video_r2_key: str,
    topic: str,
    genre: str,
    script_summary: str,
) -> dict:
    """
    Full quality scoring pipeline:
    1. Download final video from R2
    2. Extract keyframes via FFmpeg
    3. Send frames + script info to GPT-5.4 Vision (fallback GPT-5.5)
    4. Return structured score dict
    """
    # Download final video
    try:
        video_bytes = await download_bytes(final_video_r2_key)
    except Exception as e:
        logger.warning("Could not download video %s: %s — scoring without visuals", final_video_r2_key, e)
        video_bytes = None

    # Extract keyframes
    keyframes: list[bytes] = []
    if video_bytes:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(video_bytes)
            tmp_path = Path(f.name)
        try:
            for offset in _FRAME_OFFSETS[:_MAX_FRAMES]:
                try:
                    frame = await extract_keyframe(tmp_path, time_offset=offset)
                    keyframes.append(frame)
                except Exception:
                    pass   # fewer frames is OK
        finally:
            tmp_path.unlink(missing_ok=True)

    logger.info("Quality scoring: %d keyframes extracted for project %s", len(keyframes), project_id)

    # Build vision prompt
    n_frames = len(keyframes)
    user_prompt = QUALITY_USER_TEMPLATE.format(
        n_frames=n_frames if n_frames > 0 else "no",
        topic=topic,
        genre=genre,
        script_summary=script_summary[:600],
    )

    if not keyframes:
        # No video yet — score on script alone (text-only, no images)
        from .llm_service import chat_json
        try:
            result = await chat_json(QUALITY_SYSTEM, user_prompt, temperature=0.2, max_tokens=1024)
        except LLMError as e:
            raise QualityError(f"Text-only scoring failed: {e}") from e
    else:
        try:
            result = await chat_vision(
                system_prompt=QUALITY_SYSTEM,
                user_prompt=user_prompt,
                images=keyframes,
                image_media_type="image/jpeg",
                temperature=0.2,
                max_tokens=1024,
            )
        except LLMError as e:
            raise QualityError(f"Vision scoring failed: {e}") from e

    # Validate and clamp scores
    return _validate_scores(result)


def _validate_scores(raw: dict) -> dict:
    """Ensure all required fields exist and scores are within valid ranges."""
    maxes = {
        "hook_strength": 20,
        "story_coherence": 20,
        "visual_quality": 20,
        "audio_sync": 15,
        "character_consistency": 10,
        "pacing": 10,
        "engagement_potential": 5,
    }
    validated = {}
    total = 0
    for field, max_val in maxes.items():
        v = int(raw.get(field, 0))
        v = max(0, min(v, max_val))
        validated[field] = v
        total += v

    validated["overall_score"] = int(raw.get("overall_score", total))
    validated["overall_score"] = max(0, min(validated["overall_score"], 100))
    validated["gpt_feedback"] = str(raw.get("gpt_feedback", ""))
    return validated


class QualityError(Exception):
    pass
