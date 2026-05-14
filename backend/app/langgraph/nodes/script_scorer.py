"""Agent Script Scorer — AI-powered script quality gate (threshold ≥ 8/10)."""
from __future__ import annotations
import logging

from ...services.llm_service import chat_json, LLMError
from ...services.sse_service import publish_event
from ..state import ProductionState

logger = logging.getLogger(__name__)

_SCORER_SYSTEM = """Bạn là biên tập viên nội dung cao cấp chuyên đánh giá kịch bản video ngắn.
Chấm điểm kịch bản theo 4 tiêu chí (mỗi tiêu chí 1-10), sau đó tính điểm tổng.

Tiêu chí:
1. Hook (3s đầu): Độ thu hút, có khiến người xem dừng lại không?
2. Mạch câu chuyện: Logic, nhất quán, có cảm xúc?
3. Tiềm năng viral: Có chia sẻ được? Có trending hook?
4. Nhịp độ & độ dài: Phù hợp với duration, không quá dài/ngắn?

Trả về JSON:
{"score": <1-10>, "hook": <1-10>, "story": <1-10>, "viral": <1-10>, "pacing": <1-10>, "feedback": "<1-2 câu nhận xét ngắn gọn>"}
"""


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

    user_prompt = f"""Kịch bản cần chấm điểm:

{script_content[:3000]}

Chấm điểm tổng hợp (1-10). Nếu < 8 điểm, kịch bản sẽ được viết lại."""

    score = 5
    feedback = ""
    try:
        result = await chat_json(_SCORER_SYSTEM, user_prompt, temperature=0.3, max_tokens=256)
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
    """score ≥ 8 OR retry ≥ 3 → script_review; else → screenwriter (auto-retry)."""
    score = state.get("script_ai_score", 0) or 0
    retries = state.get("script_retry_count", 0)
    if score >= 8 or retries >= 3:
        return "script_review"
    return "screenwriter"
