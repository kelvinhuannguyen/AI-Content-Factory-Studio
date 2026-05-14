"""Shared LangGraph state for the AI Content Factory production pipeline."""
from __future__ import annotations
from typing import TypedDict, Optional


class ProductionState(TypedDict):
    # ── Project context (set once at start, immutable) ────────────────────
    project_id: str
    production_type: str        # "short_video" | "long_video" | "music_mv"
    topic: str
    genre: str
    style: str
    duration_seconds: int
    language: str               # "vi" | "en"

    # ── Agent Screenwriter ────────────────────────────────────────────────
    script_id: Optional[str]          # UUID của Script row trong DB
    script_content: Optional[str]     # content_raw (plain text kịch bản)
    script_html: Optional[str]        # content_html (Tiptap editor format)
    script_approved: bool             # kết quả duyệt từ human interrupt

    # ── Agent Character Designer ──────────────────────────────────────────
    character_description: Optional[str]
    character_name: Optional[str]
    characters: list[dict]            # [{id, ref_id, character_index, image_url, ...}]
    selected_character_id: Optional[str]
    character_approved: bool          # kết quả duyệt từ human interrupt
    # IP Character Pipeline fields
    extracted_characters: Optional[list]    # raw profiles from IP Architect
    character_profiles: Optional[list]      # enriched profiles with VIS + Ref IDs
    character_vis_map: Optional[dict]       # {"#CHAR_01": vis_string, "#CHAR_02": ...}
    character_count: Optional[int]          # number of characters found in script

    # ── Video Pipeline ────────────────────────────────────────────────────
    scenes: list[dict]                # [{id, scene_number, video_prompt, duration_seconds}]
    lookbook: Optional[dict]          # {ref_id: {key_identifier, constant_elements, image_url, ...}}
    shots: list[dict]                 # decomposed shots from cinematic_decomposer (≤8s each)
    video_clips: list[dict]           # [{scene_id, clip_r2_key, status}]
    voiceover_r2_key: Optional[str]
    final_video_r2_key: Optional[str]
    subtitle_r2_key: Optional[str]    # SRT file in R2
    bgm_r2_key: Optional[str]        # background music MP3 in R2
    continuity_manifest: Optional[dict]  # Master Render List from continuity_director

    # ── AI Scoring + Auto-Retry ───────────────────────────────────────────
    script_ai_score: Optional[int]   # 1-10, from script_scorer_node
    script_retry_count: int          # auto-increments on screenwriter retry
    character_ai_score: Optional[int]   # 1-10, from character_scorer_node (min across all chars)
    character_retry_count: int          # auto-increments on character auto-retry
    character_correction_briefs: Optional[dict]  # {ref_id: correction_brief_text}
    video_ai_score: Optional[int]    # 1-10, from video_validator_node
    video_retry_count: int           # auto-increments on video_editor retry
    video_review_action: Optional[str]  # "proceed" | "remake" | "hold"

    # ── Control ───────────────────────────────────────────────────────────
    current_stage: str                # tên node hiện tại
    error: Optional[str]
    approval_status: str              # "pending" | "approved" | "rejected"
    rejection_notes: Optional[str]


def initial_state(
    project_id: str,
    production_type: str = "short_video",
    topic: str = "",
    genre: str = "",
    style: str = "",
    duration_seconds: int = 60,
    language: str = "vi",
    character_description: str = "",
    character_name: str = "",
) -> ProductionState:
    """Build the initial ProductionState from a project's basic metadata."""
    return ProductionState(
        project_id=project_id,
        production_type=production_type,
        topic=topic,
        genre=genre,
        style=style,
        duration_seconds=duration_seconds,
        language=language,
        # Screenwriter
        script_id=None,
        script_content=None,
        script_html=None,
        script_approved=False,
        # Character Designer
        character_description=character_description,
        character_name=character_name,
        characters=[],
        selected_character_id=None,
        character_approved=False,
        extracted_characters=None,
        character_profiles=None,
        character_vis_map=None,
        character_count=None,
        # Video Pipeline
        scenes=[],
        lookbook=None,
        shots=[],
        video_clips=[],
        voiceover_r2_key=None,
        final_video_r2_key=None,
        subtitle_r2_key=None,
        bgm_r2_key=None,
        continuity_manifest=None,
        # AI Scoring + Auto-Retry
        script_ai_score=None,
        script_retry_count=0,
        character_ai_score=None,
        character_retry_count=0,
        character_correction_briefs=None,
        video_ai_score=None,
        video_retry_count=0,
        video_review_action=None,
        # Control
        current_stage="start",
        error=None,
        approval_status="pending",
        rejection_notes=None,
    )
