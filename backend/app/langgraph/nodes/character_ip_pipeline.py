"""Character IP Production Pipeline — helper functions for character_designer_node.

4-stage internal pipeline (all run inside character_designer_node, no separate LangGraph nodes):
  Stage 1 (Script Parser) + Stage 2 (Profiler) + Stage 3 (ID Manager): single LLM call
  Stage 4 (Prompt Engineer): pure Python, builds VIS-anchored image prompts

Industry standards applied:
  - Chuẩn 1: Character Reference ID (ref_id + VIS + deterministic seed)
  - Chuẩn 2: Fixed Seed + Unique Name (seed = character_index * 1337 + 42)
  - Chuẩn 3: Multi-Character Regional Prompting (handled by build_scene_video_prompt in prompt_templates.py)
"""
from __future__ import annotations
import logging

from ...services.llm_service import chat_json, LLMError
from ...utils.prompt_templates import CHARACTER_IP_ARCHITECT_SYSTEM, character_ip_architect_user
from ..state import ProductionState

logger = logging.getLogger(__name__)


async def _run_ip_pipeline(state: ProductionState, script_content: str) -> dict:
    """
    Stages 1-3: Single chat_json() call → character profiles with Ref IDs + VIS.
    Stage 4: Pure Python → build VIS-anchored image prompts per character.

    Returns:
      {
        character_profiles: list of full profile dicts,
        character_vis_map: {"#CHAR_01": vis_string, ...},
        main_profile: profile dict for #CHAR_01,
        supporting_profiles: list of profiles for #CHAR_02, #CHAR_03
      }

    Falls back gracefully to _build_fallback_profile() if LLM fails.
    """
    character_name_hint = state.get("character_name") or ""
    character_description_hint = state.get("character_description") or ""
    genre = state.get("genre") or "drama"
    style = state.get("style") or "cinematic"

    try:
        user_prompt = character_ip_architect_user(
            script_content=script_content,
            character_name_hint=character_name_hint,
            character_description_hint=character_description_hint,
            genre=genre,
            style=style,
        )
        result = await chat_json(
            CHARACTER_IP_ARCHITECT_SYSTEM,
            user_prompt,
            temperature=0.3,
            max_tokens=2048,
        )
        profiles: list[dict] = result.get("characters", [])
        if not isinstance(profiles, list):
            raise ValueError("IP Architect returned non-list characters")
    except (LLMError, Exception) as e:
        logger.warning("IP Architect LLM failed (falling back to user hints): %s", e)
        profiles = []

    # Fallback: build 1 minimal profile from user hints
    if not profiles:
        profiles = [_build_fallback_profile(character_name_hint, character_description_hint, genre, style)]

    # Ensure each profile has required fields
    for i, p in enumerate(profiles):
        if "ref_id" not in p or not p["ref_id"]:
            p["ref_id"] = f"#CHAR_0{i + 1}"
        if "character_index" not in p:
            p["character_index"] = i
        else:
            p["character_index"] = i  # enforce order
        if "role" not in p:
            p["role"] = "main" if i == 0 else "supporting"

    character_vis_map = {
        p["ref_id"]: p.get("visual_identity_string", p.get("name", f"character {i}"))
        for i, p in enumerate(profiles)
    }

    main_profile = profiles[0] if profiles else _build_fallback_profile(character_name_hint, character_description_hint, genre, style)
    supporting_profiles = profiles[1:] if len(profiles) > 1 else []

    logger.info(
        "IP Pipeline: extracted %d character(s): %s",
        len(profiles),
        [p.get("ref_id") for p in profiles],
    )

    return {
        "character_profiles": profiles,
        "character_vis_map": character_vis_map,
        "main_profile": main_profile,
        "supporting_profiles": supporting_profiles,
    }


def _build_image_prompt(profile: dict, user_prompt_addition: str = "") -> str:
    """
    Build VIS-anchored base prompt for image generation.
    VIS is the immutable prefix — all semantic invariants embedded.
    Deterministic seed: character_index * 1337 + 42 (Chuẩn 2).
    """
    vis = profile.get("visual_identity_string", "")
    dna = profile.get("physical_dna") or {}
    palette = profile.get("color_palette") or {}
    char_index = profile.get("character_index", 0)
    name = profile.get("name", "")

    ethnicity = dna.get("ethnicity", "")
    age = dna.get("age_range", "")
    hair = f"{dna.get('hair_color', '')} {dna.get('hair_style', '')} hair".strip()
    skin = f"{dna.get('skin_tone', '')} skin".strip()
    primary_hex = palette.get("primary", "")
    seed = char_index * 1337 + 42

    # Build the anchored prompt
    name_prefix = f"portrait of {name}: " if name else "portrait of a character: "
    base = (
        f"{name_prefix}{vis}, "
        f"consistent character identity: {ethnicity}, {age} years old, {hair}, {skin}"
    )
    if primary_hex:
        base += f", dominant color {primary_hex}"
    base += (
        f", high quality, sharp detailed face, professional studio lighting, "
        f"clean neutral background, photorealistic, seed:{seed}"
    )

    if user_prompt_addition and user_prompt_addition.strip():
        base += f", {user_prompt_addition.strip()}"

    return base


def _build_sheet_prompt(profile: dict) -> str:
    """
    Build Character Sheet prompt (Chuẩn 1 — multi-angle reference).
    Front + side view on white background for consistency reference.
    """
    vis = profile.get("visual_identity_string", "")
    char_index = profile.get("character_index", 0)
    seed = char_index * 1337 + 100  # different seed from hero portrait

    return (
        f"character design sheet: {vis}, "
        f"turnaround reference: front view on left, 3/4 angle on right, "
        f"full body portrait, white background, "
        f"concept art reference sheet, consistent character identity, "
        f"high quality, detailed face and outfit, seed:{seed}"
    )


def _build_negative_prompt(physical_dna: dict) -> str:
    """
    Build negative prompt that blocks deviations from semantic invariants.
    Prevents the image model from changing ethnicity, hair color, etc.
    """
    ethnicity = physical_dna.get("ethnicity", "")
    hair_color = physical_dna.get("hair_color", "")

    parts = []
    if ethnicity:
        parts.append(f"different ethnicity from {ethnicity}")
    if hair_color:
        parts.append(f"different hair color from {hair_color}")

    parts.extend([
        "multiple people",
        "different person",
        "face swap",
        "aged face",
        "deformed face",
        "blurry face",
        "ugly",
        "watermark",
        "text overlay",
        "logo",
    ])

    return ", ".join(parts)


def _build_fallback_profile(
    character_name: str,
    character_description: str,
    genre: str = "drama",
    style: str = "cinematic",
) -> dict:
    """
    Minimal profile built from user-provided hints.
    Used when IP Architect LLM fails or script_content is empty.
    """
    name = character_name or "Main Character"
    vis = character_description or f"a compelling {genre} character, {style} style"

    return {
        "ref_id": "#CHAR_01",
        "name": name,
        "role": "main",
        "character_index": 0,
        "scene_appearances": [],
        "physical_dna": {},
        "wardrobe_logic": "Appropriate for the narrative",
        "color_palette": {},
        "semantic_invariants": [],
        "visual_identity_string": vis,
    }
