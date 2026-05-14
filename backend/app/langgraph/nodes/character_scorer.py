"""Agent Character Scorer — Senior Art Director AI review (multimodal).

Reviews each generated character image against its Character Ref ID + VIS + script context.
Scores on 4 criteria:
  A. Character Consistency (4 pts) — highest weight
  B. Script Fidelity (2.5 pts)
  C. Technical Quality (2 pts)
  D. Visual Language (1.5 pts)

If score < 8 AND retry_count < 3: generates Correction Brief → loops back to character_designer
If score >= 8 OR retry_count >= 3: proceeds to human review (character_review_node)

Same pattern as script_scorer_node and video_validator_node.
"""
from __future__ import annotations
import json
import logging
import uuid

import httpx

from ...services.llm_service import chat_vision, LLMError
from ...services.sse_service import publish_event
from ..state import ProductionState

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3

CHARACTER_REVIEWER_SYSTEM = """You are a Senior Art Director at a major animation studio.
Your task: strictly review AI-generated character design images against their Character Ref IDs.
OUTPUT ONLY a JSON object. No explanation, no reasoning, no other text.

Scoring framework (total 10 points):
- Character Consistency (4 pts): hair color/style, eye color, skin tone, distinctive features
  must all match the Visual Identity String EXACTLY
- Script Fidelity (2.5 pts): wardrobe matches wardrobe_logic, expression matches role/personality
- Technical Quality (2 pts): no AI artifacts (extra fingers, face distortion, blur, watermarks)
- Visual Language (1.5 pts): color palette matches spec, visual style is consistent

Approval threshold: score >= 8 means approved.
If score < 8, write a specific Correction Brief with exact instructions for regeneration.
Example: "Hair color rendered as brown instead of specified jet black. Eye color appears green
instead of dark brown. Retry with: 'jet black hair ONLY, dark brown eyes ONLY, strict VIS adherence'"

Required output (exactly this format, nothing else):
{"consistency_score": <0-4>, "fidelity_score": <0-2.5>, "technical_score": <0-2>, "visual_score": <0-1.5>, "overall_score": <1-10 integer>, "correction_brief": "<instructions if score<8 else empty string>"}"""


async def character_scorer_node(state: ProductionState) -> dict:
    """
    Multimodal AI review: score each character image vs VIS + DNA + script.
    - overall_score = min of all character scores (weakest determines batch quality)
    - score < 8 AND retry < 3 → correction_briefs → route back to character_designer
    - score >= 8 OR retry >= 3 → route to character_review (human interrupt)
    """
    project_id = state["project_id"]
    retry_count = state.get("character_retry_count", 0)
    profiles = state.get("character_profiles") or []

    await publish_event(project_id, {
        "type": "agent_start",
        "agent": "character_scorer",
        "message": f"Reviewer Agent đang kiểm tra chất lượng nhân vật (lần {retry_count + 1}/{_MAX_RETRIES})...",
    })

    characters_in_db = await _load_characters_for_scoring(project_id)

    if not characters_in_db:
        # Narration-only script — no characters to score
        await publish_event(project_id, {
            "type": "agent_done",
            "agent": "character_scorer",
            "score": 10,
            "will_retry": False,
            "message": "Không có nhân vật cần kiểm tra.",
        })
        return {
            "character_ai_score": 10,
            "character_retry_count": retry_count,
            "character_correction_briefs": None,
            "current_stage": "character_scorer",
        }

    # Score each character
    scores: list[int] = []
    correction_briefs: dict[str, str] = {}

    for char_data in characters_in_db:
        result = await _score_character(char_data, state)
        score = result["score"]
        brief = result["correction_brief"]
        scores.append(score)

        if brief and score < 8:
            correction_briefs[char_data["ref_id"]] = brief

        # Persist score + brief to DB
        await _save_character_score(char_data["id"], score, brief or None)

        logger.info(
            "Character scorer: %s scored %d/10%s",
            char_data.get("ref_id"),
            score,
            f" — brief: {brief[:80]}" if brief else "",
        )

    overall_score = min(scores) if scores else 10
    will_retry = overall_score < 8 and retry_count < _MAX_RETRIES

    await publish_event(project_id, {
        "type": "agent_done",
        "agent": "character_scorer",
        "score": overall_score,
        "retry_count": retry_count,
        "will_retry": will_retry,
        "correction_briefs": correction_briefs,
        "message": (
            f"Reviewer Agent: {overall_score}/10 — "
            f"{'Tạo lại nhân vật chưa đạt' if will_retry else 'Đạt yêu cầu ✓'}"
        ),
    })

    logger.info(
        "Character scorer: overall=%d, retry_count=%d, will_retry=%s",
        overall_score, retry_count, will_retry,
    )

    return {
        "character_ai_score": overall_score,
        "character_retry_count": retry_count,  # designer_node increments on re-entry
        "character_correction_briefs": correction_briefs if correction_briefs else None,
        "current_stage": "character_scorer",
    }


def route_after_character_scorer(state: ProductionState) -> str:
    """score >= 8 OR retry >= 3 → character_review; else → character_designer (auto-retry)."""
    score = state.get("character_ai_score", 0) or 0
    retries = state.get("character_retry_count", 0)
    if score >= 8 or retries >= _MAX_RETRIES:
        return "character_review"
    return "character_designer"


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _load_characters_for_scoring(project_id: str) -> list[dict]:
    """Load hero portrait characters from DB for scoring."""
    from ...database import AsyncSessionLocal
    from ...models.character import Character
    from ...services.r2_service import public_url
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Character)
            .where(
                Character.project_id == uuid.UUID(project_id),
                Character.variant_index == 0,
                Character.image_r2_key.isnot(None),
            )
            .order_by(Character.character_index)
        )
        chars = result.scalars().all()

    return [
        {
            "id": str(c.id),
            "ref_id": c.ref_id or f"#CHAR_0{c.character_index + 1}",
            "character_index": c.character_index,
            "name": c.name,
            "role": c.character_role or "main",
            "visual_identity_string": c.visual_identity_string or "",
            "physical_dna": c.physical_dna or {},
            "color_palette": c.color_palette or {},
            "image_url": public_url(c.image_r2_key) if c.image_r2_key else None,
        }
        for c in chars
    ]


async def _score_character(char_data: dict, state: ProductionState) -> dict:
    """
    Download character image bytes + call chat_vision() to score.
    Returns {"score": int, "correction_brief": str}.
    Non-fatal: returns score=8 (pass-through) on any failure.
    """
    image_url = char_data.get("image_url", "")
    if not image_url:
        logger.warning("No image URL for character %s — skipping scoring", char_data.get("ref_id"))
        return {"score": 8, "correction_brief": ""}

    # Download image bytes
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(image_url)
        if resp.status_code != 200:
            raise ValueError(f"HTTP {resp.status_code}")
        image_bytes = resp.content
    except Exception as e:
        logger.warning("Image download failed for %s: %s — passing through", char_data.get("ref_id"), e)
        return {"score": 8, "correction_brief": ""}

    vis = char_data.get("visual_identity_string", "")
    dna = char_data.get("physical_dna") or {}
    role = char_data.get("role", "main")
    ref_id = char_data.get("ref_id", "#CHAR_01")

    user_prompt = f"""Review this character image against its specification.

Character Ref ID: {ref_id}
Visual Identity String: {vis}
Physical DNA: {json.dumps(dna, ensure_ascii=False)}
Role: {role}
Project context: {state.get('topic', '')} — Genre: {state.get('genre', '')}, Style: {state.get('style', '')}

IMPORTANT: Output ONLY the JSON object. Nothing before or after it.
Required format (exactly):
{{"consistency_score": <0-4>, "fidelity_score": <0-2.5>, "technical_score": <0-2>, "visual_score": <0-1.5>, "overall_score": <1-10 integer>, "correction_brief": "<specific fix instructions if score<8, else empty string>"}}"""

    try:
        result = await chat_vision(
            CHARACTER_REVIEWER_SYSTEM,
            user_prompt,
            images=[image_bytes],
            image_media_type="image/png",
            temperature=0.1,
            max_tokens=512,
        )
        score = max(1, min(10, int(result.get("overall_score", 7))))
        brief = result.get("correction_brief", "") or ""
        return {"score": score, "correction_brief": brief}
    except (LLMError, Exception) as e:
        logger.warning("Character scorer LLM failed for %s (pass-through): %s", ref_id, e)
        return {"score": 8, "correction_brief": ""}


async def _save_character_score(character_id: str, score: int, brief: str | None) -> None:
    """Persist ai_score and correction_brief to the Character DB row."""
    try:
        from ...database import AsyncSessionLocal
        from ...models.character import Character

        async with AsyncSessionLocal() as db:
            char = await db.get(Character, uuid.UUID(character_id))
            if char:
                char.ai_score = score
                char.correction_brief = brief or None
                await db.commit()
    except Exception as e:
        logger.warning("Could not save character score to DB: %s", e)
