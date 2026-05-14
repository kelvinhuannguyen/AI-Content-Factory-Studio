"""Agent SEO & Viral Strategist — Agent 8.

Runs after video_review approval (proceed/hold).
Generates A/B SEO packages: Package A = SEO-optimized, Package B = Viral/Clickbait.
Sends email with SEO preview + [Duyệt A] / [Duyệt B] / [Viết lại] buttons.
Human approves via email or dashboard → seo_review_node resumes.
On approval → generate thumbnail → END.
"""
from __future__ import annotations
import logging
import uuid

from langgraph.types import interrupt

from ...services.sse_service import publish_event
from ..state import ProductionState

logger = logging.getLogger(__name__)


async def seo_agent_node(state: ProductionState) -> dict:
    """
    SEO & Viral Strategist node.
    1. Load project context (script, characters, blueprint)
    2. Generate A/B SEO packages via Claude
    3. Save to SeoPackage DB
    4. Send email with SEO preview
    5. Return seo_package to state
    """
    project_id = state["project_id"]
    retry = state.get("seo_retry_count", 0)

    await publish_event(project_id, {
        "type": "agent_start",
        "agent": "seo_agent",
        "message": f"SEO Agent đang tạo gói metadata A/B{'(lần ' + str(retry + 1) + ')' if retry > 0 else ''}...",
    })

    # ── 1. Load project context ───────────────────────────────────────────────
    from ...database import AsyncSessionLocal
    from ...models.project import Project
    from ...models.script import Script
    from ...models.character import Character
    from ...models.seo_package import SeoPackage
    from sqlalchemy import select, delete

    pid = uuid.UUID(project_id)
    async with AsyncSessionLocal() as db:
        proj = await db.get(Project, pid)
        project_title = proj.title if proj else "Dự án mới"
        topic    = (proj.topic or "") if proj else ""
        genre    = (proj.genre or "") if proj else ""
        style    = (proj.style or "") if proj else ""
        language = (proj.preferred_language or "vi") if proj else "vi"
        total_dur = (proj.duration_seconds or 60) if proj else 60

        # Latest script
        script_result = await db.execute(
            select(Script).where(Script.project_id == pid).order_by(Script.version.desc())
        )
        script = script_result.scalars().first()
        script_summary = (script.content_raw or "")[:500] if script else ""

        # Character names for thumbnail prompt
        char_result = await db.execute(
            select(Character)
            .where(Character.project_id == pid, Character.variant_index == 0)
            .order_by(Character.character_index)
        )
        chars = char_result.scalars().all()
        character_names = [c.ref_id for c in chars if c.ref_id]

    # ── 2. Generate A/B SEO packages ─────────────────────────────────────────
    from ...services.llm_service import chat_json, LLMError
    from ...utils.prompt_templates import SEO_AB_SYSTEM, seo_ab_user

    seo_package: dict = {}
    try:
        user_prompt = seo_ab_user(
            topic=topic,
            genre=genre,
            style=style,
            script_summary=script_summary,
            language=language,
            character_names=character_names,
            total_duration_s=total_dur,
        )
        result = await chat_json(SEO_AB_SYSTEM, user_prompt, temperature=0.7, max_tokens=3000)
        seo_package = {
            "package_a": result.get("package_a", {}),
            "package_b": result.get("package_b", {}),
            "selected": "a",  # default
        }
    except (LLMError, Exception) as e:
        logger.warning("SEO generation failed: %s", e)
        # Fallback: use existing seo.py single-package if available
        seo_package = {"package_a": {}, "package_b": {}, "selected": "a", "error": str(e)}

    # ── 3. Save to SeoPackage DB (package_a as default) ──────────────────────
    pkg_a = seo_package.get("package_a", {})
    pkg_b = seo_package.get("package_b", {})
    if pkg_a:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(SeoPackage).where(SeoPackage.project_id == pid))
            # Store combined package: title_variants = [a_seo, a_clickbait, a_story, b_seo, b_clickbait, b_story]
            seo_row = SeoPackage(
                project_id=pid,
                title_variants=[
                    pkg_a.get("title_seo", ""),
                    pkg_a.get("title_clickbait", ""),
                    pkg_a.get("title_story", ""),
                    pkg_b.get("title_seo", ""),
                    pkg_b.get("title_clickbait", ""),
                    pkg_b.get("title_story", ""),
                ],
                description=pkg_a.get("description", ""),
                tags=pkg_a.get("tags", []),
                thumbnail_prompt=pkg_a.get("thumbnail_prompt", ""),
            )
            db.add(seo_row)
            await db.commit()

    # ── 4. Send SEO review email ──────────────────────────────────────────────
    try:
        from ...services.notification_service import send_seo_review_request
        await send_seo_review_request(
            project_id=project_id,
            project_title=project_title,
            seo_package=seo_package,
        )
    except Exception as e:
        logger.warning("SEO email failed: %s", e)

    await publish_event(project_id, {
        "type": "agent_done",
        "agent": "seo_agent",
        "has_package_a": bool(pkg_a),
        "has_package_b": bool(pkg_b),
        "message": "Gói SEO A/B đã tạo xong — đã gửi email duyệt.",
    })

    return {
        "seo_package": seo_package,
        "current_stage": "seo_agent",
    }


async def seo_review_node(state: ProductionState) -> dict:
    """
    Human SEO Review (INTERRUPT):
    - User selects Package A or B, or requests rewrite
    - Resumes with {"approved": bool, "selected_package": "a"|"b"}
    """
    project_id = state["project_id"]

    await publish_event(project_id, {
        "type": "agent_interrupt",
        "step": "seo_review",
        "message": "Đang chờ duyệt gói SEO — kiểm tra email hoặc dashboard.",
    })

    decision: dict = interrupt({
        "step": "seo_review",
        "seo_package": state.get("seo_package"),
        "project_id": project_id,
        "video_url": state.get("final_video_r2_key"),
        "video_ai_score": state.get("video_ai_score"),
        "tech_audit": state.get("video_tech_audit"),
    })

    approved = decision.get("approved", True)
    selected = decision.get("selected_package", "a")

    if approved:
        # Generate thumbnail (non-fatal)
        await _generate_thumbnail(project_id, state.get("seo_package"), selected)

    return {
        "approval_status": "approved" if approved else "pending",
        "seo_package": {**(state.get("seo_package") or {}), "selected": selected},
        "seo_retry_count": 0 if approved else (state.get("seo_retry_count", 0) + 1),
        "current_stage": "seo_review",
    }


def route_after_seo_review(state: ProductionState) -> str:
    """approve → end; reject (retry ≤ 3) → seo_agent; retry > 3 → end anyway."""
    approved = state.get("approval_status") == "approved"
    retries  = state.get("seo_retry_count", 0)
    if approved or retries >= 3:
        return "end"
    return "seo_agent"


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _generate_thumbnail(project_id: str, seo_package: dict | None, selected: str) -> None:
    """Generate thumbnail image for the selected SEO package. Non-fatal."""
    if not seo_package:
        return
    pkg = seo_package.get(f"package_{selected}", seo_package.get("package_a", {}))
    thumb_prompt = pkg.get("thumbnail_prompt", "")
    if not thumb_prompt:
        return
    try:
        from ...services.image_fallback_service import generate_image
        from ...services.r2_service import upload_bytes
        from ...database import AsyncSessionLocal
        from ...models.seo_package import SeoPackage
        from sqlalchemy import select

        pid = uuid.UUID(project_id)
        img_bytes = await generate_image(thumb_prompt, variant_index=0)
        r2_key = f"projects/{project_id}/thumbnail.jpg"
        await upload_bytes(r2_key, img_bytes, content_type="image/jpeg")

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(SeoPackage).where(SeoPackage.project_id == pid).limit(1)
            )
            seo_row = result.scalars().first()
            if seo_row:
                seo_row.thumbnail_r2_key = r2_key
            await db.commit()
        logger.info("SEO thumbnail generated: %s", r2_key)
    except Exception as e:
        logger.warning("Thumbnail generation failed (non-fatal): %s", e)
