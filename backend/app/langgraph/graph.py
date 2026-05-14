"""LangGraph StateGraph — 14 nodes, 3 interrupt points (Pipeline v3).

Graph flow — 3 Trạm (checkpoints):
  screenwriter → script_scorer → character_designer  [auto, no interrupt]
  → character_scorer → character_review(INTERRUPT 1 — Trạm 1: Production Bible)
  → scene_planner → cinematic_decomposer  [auto, no interrupt]
  → shot_review(INTERRUPT 2 — Trạm 2: Storyboard & Shot List)
  → continuity_director → video_editor → final_assembler
  → video_validator → seo_agent  [auto, no interrupt]
  → seo_review(INTERRUPT 3 — Trạm 3: Final Master)
  → END
"""
from __future__ import annotations
import logging
from langgraph.graph import StateGraph, END

from .state import ProductionState
from .nodes.screenwriter import (
    screenwriter_node,
    script_review_node,
    route_after_script_review,
)
from .nodes.script_scorer import (
    script_scorer_node,
    route_after_script_scorer,
)
from .nodes.character_designer import (
    character_designer_node,
    character_review_node,
    route_after_character_review,
)
from .nodes.character_scorer import (
    character_scorer_node,
    route_after_character_scorer,
)
from .nodes.scene_planner import (
    scene_planner_node,
    scene_review_node,
    route_after_scene_review,
)
from .nodes.cinematic_decomposer import cinematic_decomposer_node
from .nodes.shot_review import shot_review_node, route_after_shot_review
from .nodes.continuity_director import continuity_director_node
from .nodes.final_assembler import final_assembler_node
from .nodes.seo_agent import seo_agent_node, seo_review_node, route_after_seo_review
from .nodes.video_editor import video_editor_node
from .nodes.video_validator import (
    video_validator_node,
    route_after_video_validator,
)

logger = logging.getLogger(__name__)

_graph = None


def _build_graph():
    builder = StateGraph(ProductionState)

    # ── Node registration ─────────────────────────────────────────────────
    builder.add_node("screenwriter",       screenwriter_node)
    builder.add_node("script_scorer",      script_scorer_node)
    builder.add_node("script_review",      script_review_node)       # pass-through, no interrupt
    builder.add_node("character_designer", character_designer_node)
    builder.add_node("character_scorer",   character_scorer_node)
    builder.add_node("character_review",   character_review_node)    # INTERRUPT 1 — Trạm 1
    builder.add_node("scene_planner",      scene_planner_node)
    builder.add_node("scene_review",       scene_review_node)        # pass-through, no interrupt
    builder.add_node("cinematic_decomposer", cinematic_decomposer_node)
    builder.add_node("shot_review",        shot_review_node)         # INTERRUPT 2 — Trạm 2
    builder.add_node("continuity_director", continuity_director_node)
    builder.add_node("video_editor",       video_editor_node)
    builder.add_node("final_assembler",    final_assembler_node)
    builder.add_node("video_validator",    video_validator_node)
    builder.add_node("seo_agent",          seo_agent_node)
    builder.add_node("seo_review",         seo_review_node)          # INTERRUPT 3 — Trạm 3

    # ── Entry point ───────────────────────────────────────────────────────
    builder.set_entry_point("screenwriter")

    # ── Script flow (no human interrupt) ─────────────────────────────────
    builder.add_edge("screenwriter", "script_scorer")
    builder.add_conditional_edges(
        "script_scorer",
        route_after_script_scorer,
        {"character_designer": "character_designer", "screenwriter": "screenwriter"},
    )
    # script_review is a pass-through kept for import compatibility; not used in routing

    # ── Character flow — Trạm 1 ───────────────────────────────────────────
    builder.add_edge("character_designer", "character_scorer")
    builder.add_conditional_edges(
        "character_scorer",
        route_after_character_scorer,
        {"character_designer": "character_designer", "character_review": "character_review"},
    )
    builder.add_conditional_edges(
        "character_review",
        route_after_character_review,
        {"scene_planner": "scene_planner", "character_designer": "character_designer"},
    )

    # ── Scene flow (no human interrupt, auto-approves) ────────────────────
    builder.add_edge("scene_planner", "scene_review")
    builder.add_conditional_edges(
        "scene_review",
        route_after_scene_review,
        {"video_editor": "cinematic_decomposer", "scene_planner": "scene_planner"},
    )

    # ── Trạm 2: Shot review after cinematic decomposer ────────────────────
    builder.add_edge("cinematic_decomposer", "shot_review")
    builder.add_conditional_edges(
        "shot_review",
        route_after_shot_review,
        {"continuity_director": "continuity_director", "scene_planner": "scene_planner"},
    )
    builder.add_edge("continuity_director", "video_editor")

    # ── Video pipeline (no human gate) ───────────────────────────────────
    builder.add_edge("video_editor",    "final_assembler")
    builder.add_edge("final_assembler", "video_validator")
    builder.add_conditional_edges(
        "video_validator",
        route_after_video_validator,
        {"seo_agent": "seo_agent", "video_editor": "video_editor"},
    )

    # ── Trạm 3: SEO + Final Master ───────────────────────────────────────
    builder.add_edge("seo_agent", "seo_review")
    builder.add_conditional_edges(
        "seo_review",
        route_after_seo_review,
        {"end": END, "seo_agent": "seo_agent"},
    )

    return builder


async def get_graph():
    """Return singleton compiled graph with MemorySaver checkpointer."""
    global _graph
    if _graph is None:
        from .checkpointer import get_checkpointer
        checkpointer = await get_checkpointer()
        _graph = _build_graph().compile(checkpointer=checkpointer)
        logger.info("LangGraph compiled: 16 nodes, 3 interrupt points (Pipeline v3)")
    return _graph
