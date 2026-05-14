"""LangGraph StateGraph — 14 nodes, 5 interrupt points.

Graph flow:
  screenwriter → script_scorer → script_review(INTERRUPT) → character_designer
    ↑ retry < 8/10                ↑ human reject loops back
  → character_scorer → character_review(INTERRUPT) → scene_planner → scene_review(INTERRUPT)
     ↑ AI retry < 8/10   ↑ human reject loops back to character_designer
  → cinematic_decomposer → continuity_director → video_editor → video_validator → video_review(INTERRUPT) → END
                                                                  ↑ AI retry < 8/10  ↑ remake loops back
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
from .nodes.continuity_director import continuity_director_node
from .nodes.video_editor import video_editor_node
from .nodes.video_validator import (
    video_validator_node,
    video_review_node,
    route_after_video_validator,
    route_after_video_review,
)

logger = logging.getLogger(__name__)

_graph = None


def _build_graph():
    builder = StateGraph(ProductionState)

    # ── Node registration ─────────────────────────────────────────────────
    builder.add_node("screenwriter",       screenwriter_node)
    builder.add_node("script_scorer",      script_scorer_node)
    builder.add_node("script_review",      script_review_node)
    builder.add_node("character_designer", character_designer_node)
    builder.add_node("character_scorer",   character_scorer_node)
    builder.add_node("character_review",   character_review_node)
    builder.add_node("scene_planner",           scene_planner_node)
    builder.add_node("scene_review",            scene_review_node)
    builder.add_node("cinematic_decomposer",    cinematic_decomposer_node)
    builder.add_node("continuity_director",     continuity_director_node)
    builder.add_node("video_editor",            video_editor_node)
    builder.add_node("video_validator",    video_validator_node)
    builder.add_node("video_review",       video_review_node)

    # ── Entry point ───────────────────────────────────────────────────────
    builder.set_entry_point("screenwriter")

    # ── Script flow ───────────────────────────────────────────────────────
    builder.add_edge("screenwriter", "script_scorer")
    builder.add_conditional_edges(
        "script_scorer",
        route_after_script_scorer,
        {"script_review": "script_review", "screenwriter": "screenwriter"},
    )
    builder.add_conditional_edges(
        "script_review",
        route_after_script_review,
        {"character_designer": "character_designer", "screenwriter": "screenwriter"},
    )

    # ── Character flow ────────────────────────────────────────────────────
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

    # ── Scene flow ────────────────────────────────────────────────────────
    builder.add_edge("scene_planner", "scene_review")
    builder.add_conditional_edges(
        "scene_review",
        route_after_scene_review,
        # approved → cinematic_decomposer (intercept before video_editor); rejected → scene_planner
        {"video_editor": "cinematic_decomposer", "scene_planner": "scene_planner"},
    )
    builder.add_edge("cinematic_decomposer", "continuity_director")
    builder.add_edge("continuity_director",  "video_editor")

    # ── Video pipeline ────────────────────────────────────────────────────
    builder.add_edge("video_editor", "video_validator")
    builder.add_conditional_edges(
        "video_validator",
        route_after_video_validator,
        {"video_review": "video_review", "video_editor": "video_editor"},
    )
    builder.add_conditional_edges(
        "video_review",
        route_after_video_review,
        {"end": END, "video_editor": "video_editor"},
    )

    return builder


async def get_graph():
    """Return singleton compiled graph with MemorySaver checkpointer."""
    global _graph
    if _graph is None:
        from .checkpointer import get_checkpointer
        checkpointer = await get_checkpointer()
        _graph = _build_graph().compile(checkpointer=checkpointer)
        logger.info("LangGraph compiled: 14 nodes, 5 interrupt points")
    return _graph
