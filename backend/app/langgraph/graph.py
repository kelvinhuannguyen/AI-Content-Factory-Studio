"""LangGraph StateGraph — kết nối các agent + interrupt config.

Phase 1 graph (Sprint 4-5):
  screenwriter → script_review(interrupt) → character_designer
  → character_review(interrupt) → scene_planner
  → scene_review(interrupt) → video_generator → END
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
from .nodes.character_designer import (
    character_designer_node,
    character_review_node,
)
from .nodes.scene_planner import (
    scene_planner_node,
    scene_review_node,
    route_after_scene_review,
)
from .nodes.video_generator import video_generator_node

logger = logging.getLogger(__name__)

_graph = None


def _build_graph():
    builder = StateGraph(ProductionState)

    # ── Nodes ────────────────────────────────────────────────────────────
    builder.add_node("screenwriter",       screenwriter_node)
    builder.add_node("script_review",      script_review_node)
    builder.add_node("character_designer", character_designer_node)
    builder.add_node("character_review",   character_review_node)
    builder.add_node("scene_planner",      scene_planner_node)
    builder.add_node("scene_review",       scene_review_node)
    builder.add_node("video_generator",    video_generator_node)

    # ── Edges ────────────────────────────────────────────────────────────
    builder.set_entry_point("screenwriter")

    # Script flow
    builder.add_edge("screenwriter", "script_review")
    builder.add_conditional_edges(
        "script_review",
        route_after_script_review,
        {"character_designer": "character_designer", "screenwriter": "screenwriter"},
    )

    # Character flow
    builder.add_edge("character_designer", "character_review")
    builder.add_edge("character_review", "scene_planner")   # always proceed after character selection

    # Scene flow
    builder.add_edge("scene_planner", "scene_review")
    builder.add_conditional_edges(
        "scene_review",
        route_after_scene_review,
        {"video_generator": "video_generator", "scene_planner": "scene_planner"},
    )

    # Video generation → END (Celery handles rest asynchronously)
    builder.add_edge("video_generator", END)

    return builder


async def get_graph():
    """Return singleton compiled graph with AsyncRedisSaver checkpointer."""
    global _graph
    if _graph is None:
        from .checkpointer import get_checkpointer
        checkpointer = await get_checkpointer()
        _graph = _build_graph().compile(checkpointer=checkpointer)
        logger.info("LangGraph compiled: 7 nodes, 3 interrupt points")
    return _graph
