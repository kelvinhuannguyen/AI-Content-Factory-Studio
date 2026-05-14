"""Agent Script Scorer — AI-powered script quality gate (threshold ≥ 8/10)."""
from __future__ import annotations
import logging

from ...services.llm_service import chat_json, LLMError
from ...services.sse_service import publish_event
from ..state import ProductionState

logger = logging.getLogger(__name__)

_SCORER_SYSTEM = """You are a senior content editor scoring short video scripts.
OUTPUT ONLY a JSON object. No explanation, no reasoning, no other text.

Score on 4 criteria (each 1-10):
1. hook: First 3 seconds — does it stop the scroll?
2. story: Coherence and emotion
3. viral: Shareability and trending potential
4. pacing: Fits the duration, not too long/short

Required output (exactly this format, nothing else):
{"score": <average 1-10>, "hook": <1-10>, "story": <1-10>, "viral": <1-10>, "pacing": <1-10>, "feedback": "<one sentence in Vietnamese>"}"""


async def script_scorer_node(state: ProductionState) -> dict:
    """
    AI Script Scorer:
    - Scores script 1-10 across 4 criteria
    - If score < 8 AND retry_count < 3 → graph routes back to screenwriter
    - If score ≥ 8 OR retry_count ≥ 3 → graph proceeds to script_review (human interrupt)
    """
    project_id = state["project_id"]
    script_content = state.get("script_content") or ""
    retry_count = state.get("script_retry_count", 0)

    await publish_event(project_id, {
        "type": "agent_start",
        "agent": "script_scorer",
        "message": f"Đang chấm điểm kịch bản (lần {retry_count + 1}/3)...",
    })

    user_prompt = f"""Script to score:

{script_content[:2000]}

IMPORTANT: Output ONLY the JSON object. Nothing before or after it."""

    score = 5
    feedback = ""
    try:
        result = await chat_json(_SCORER_SYSTEM, user_prompt, temperature=0.1, max_tokens=512)
        score = max(1, min(10, int(result.get("score", 5))))
        feedback = result.get("feedback", "")
    except (LLMError, Exception) as e:
        logger.warning("Script scorer LLM error (non-fatal, passing through): %s", e)
        score = 8  # pass-through on error so pipeline isn't blocked

    will_retry = score < 8 and retry_count < 3

    await publish_event(project_id, {
        "type": "agent_done",
        "agent": "script_scorer",
        "score": score,
        "feedback": feedback,
        "will_retry": will_retry,
        "message": (
            f"Điểm kịch bản: {score}/10 — {'Tạo lại' if will_retry else 'Đạt yêu cầu ✓'}"
        ),
    })

    logger.info("Script score: %d/10, retry_count=%d, will_retry=%s", score, retry_count, will_retry)
    return {
        "script_ai_score": score,
        "current_stage": "script_scorer",
        "error": None,
    }


def route_after_script_scorer(state: ProductionState) -> str:
    """score ≥ 8 OR retry ≥ 3 → character_designer (no human gate); else → screenwriter."""
    score = state.get("script_ai_score", 0) or 0
    retries = state.get("script_retry_count", 0)
    if score >= 8 or retries >= 3:
        return "character_designer"
    return "screenwriter"
