"""All LLM prompt templates. Keep prompts here so API endpoints stay thin."""

# ── Topic trending analysis ──────────────────────────────────────────────
TOPIC_TRENDING_SYSTEM = """Bạn là chuyên gia phân tích xu hướng nội dung YouTube và mạng xã hội.
Nhiệm vụ: phân tích danh sách video đang trending và đề xuất 10 chủ đề video phù hợp.
Luôn trả lời bằng JSON hợp lệ theo đúng schema được yêu cầu. Không thêm markdown, không giải thích ngoài JSON."""

def topic_trending_user(
    raw_titles: list[str],
    genre: str,
    style: str,
    production_type: str,
    language: str = "vi",
) -> str:
    lang_label = "tiếng Việt" if language == "vi" else "English"
    type_label = {
        "short_video": "video ngắn (Reels/Shorts/TikTok)",
        "long_video":  "video dài YouTube",
        "music_mv":    "MV ca nhạc",
    }.get(production_type, "video")
    return f"""Dựa trên các video đang trending trên YouTube:
{chr(10).join(f"- {t}" for t in raw_titles[:20])}

Hãy đề xuất 10 chủ đề {type_label} theo thể loại "{genre}", phong cách "{style}", viết bằng {lang_label}.

Trả về JSON array với đúng format sau:
[
  {{
    "title": "Tiêu đề video hấp dẫn",
    "hook": "Câu hook mở đầu (tại sao người xem phải click)",
    "rationale": "Lý do xu hướng này đang hot (1-2 câu)",
    "trend_score": 85
  }}
]

Đảm bảo:
- Tiêu đề bắt đầu bằng số, câu hỏi, hoặc tuyên bố gây tò mò
- Hook phải gây shock hoặc kích thích sự tò mò trong 3 giây
- trend_score từ 60-99 dựa trên tiềm năng viral
- Phù hợp văn hóa và xu hướng {lang_label}"""


# ── Script generation ────────────────────────────────────────────────────
SCRIPT_SYSTEM = """Bạn là biên kịch chuyên nghiệp với kinh nghiệm viết kịch bản Hollywood và nội dung viral YouTube.
Nhiệm vụ: viết kịch bản video hoàn chỉnh theo yêu cầu.
Luôn trả lời bằng JSON hợp lệ. Không thêm markdown bên ngoài JSON."""

def script_user(
    topic: str,
    genre: str,
    style: str,
    duration_seconds: int,
    production_type: str,
    language: str = "vi",
    additional_notes: str = "",
) -> str:
    lang_label = "tiếng Việt" if language == "vi" else "English"
    type_label = {
        "short_video": "video ngắn (9:16 dọc, tối ưu TikTok/Reels/Shorts)",
        "long_video":  "video dài YouTube (16:9 ngang)",
        "music_mv":    "MV ca nhạc",
    }.get(production_type, "video")

    minutes = duration_seconds // 60
    seconds = duration_seconds % 60
    dur_label = f"{minutes} phút {seconds} giây" if minutes else f"{seconds} giây"

    extra = f"\nYêu cầu bổ sung: {additional_notes}" if additional_notes.strip() else ""

    return f"""Viết kịch bản {type_label} cho:
- Chủ đề: {topic}
- Thể loại: {genre}
- Phong cách: {style}
- Thời lượng: {dur_label}
- Ngôn ngữ: {lang_label}{extra}

Yêu cầu kịch bản:
1. Hook cực mạnh trong 3 giây đầu — phải khiến người xem không thể dừng cuộn
2. Cấu trúc 3 hồi Hollywood (Hook → Nội dung chính → CTA)
3. Có lời thoại/narration cụ thể cho giọng đọc (voice-over)
4. Có mô tả cảnh quay (shot description) cho từng đoạn
5. Ước tính thời gian cho từng đoạn

Trả về JSON với format:
{{
  "title": "Tiêu đề video",
  "hook": "Câu hook 3 giây đầu",
  "total_estimated_seconds": {duration_seconds},
  "word_count": 0,
  "scenes": [
    {{
      "scene_number": 1,
      "title": "Tên cảnh",
      "duration_seconds": 5,
      "narration": "Lời thoại/narration đọc trong cảnh này...",
      "shot_description": "Mô tả hình ảnh: góc quay, nhân vật, hành động, mood...",
      "on_screen_text": "Chữ hiển thị trên màn hình (nếu có)"
    }}
  ],
  "full_script_text": "Toàn bộ kịch bản dạng văn bản thuần (cho editor)"
}}"""


# ── Scene breakdown → video prompts ─────────────────────────────────────
SCENE_PROMPT_SYSTEM = """You are an expert at creating prompts for AI video generation (Seedance, Kling AI, RunwayML).
Task: convert scene descriptions into optimized video prompts for AI.
When a character_vis_map is provided, embed the Visual Identity String verbatim for each character present.
Return ONLY valid JSON. No markdown, no explanation outside JSON."""

def scene_prompt_user(
    scene_title: str,
    shot_description: str,
    narration: str,
    character_description: str,
    genre: str,
    style: str,
    production_type: str,
    vis_map: dict | None = None,
) -> str:
    aspect = "9:16 vertical" if production_type == "short_video" else "16:9 widescreen"

    if vis_map:
        char_lines = "\n".join(
            f"  - {ref_id}: {vis}" for ref_id, vis in vis_map.items()
        )
        char_section = f"""- CHARACTER VISUAL IDENTITY MAP (immutable — do not deviate):
{char_lines}
- Detect which characters from the map are PHYSICALLY PRESENT in this scene based on the action.
  Return their ref_ids in the characters_in_scene field."""
        chars_field = '"characters_in_scene": ["#CHAR_01"]'
    else:
        char_section = f"- Nhân vật: {character_description}"
        chars_field = '"characters_in_scene": []'

    return f"""Create a video prompt for AI video generation from this scene:
- Scene: {scene_title}
- Description: {shot_description}
- Narration: {narration}
{char_section}
- Genre: {genre} | Style: {style} | Aspect: {aspect}

CHARACTER CONSISTENCY RULES (when vis_map provided):
- Each character's VIS is their semantic invariant — embed it verbatim if they appear
- Do NOT mix traits between characters
- If 2+ characters appear together, note both ref_ids in characters_in_scene

Return JSON:
{{
  "video_prompt": "Detailed English prompt for Seedance/Kling: subject, action, environment, camera movement, lighting, mood, style. Min 50 words.",
  "negative_prompt": "What to avoid (blur, watermark, text, ugly, deformed...)",
  {chars_field}
}}"""


# ── Character IP Architect (Industry-standard IP character pipeline) ──────
CHARACTER_IP_ARCHITECT_SYSTEM = """You are a Character IP Architect for a professional video production pipeline.
Your task: analyze the video script, extract ALL named or implied characters, and build complete "Character DNA" profiles.

CRITICAL RULE: Every physical trait you define is a SEMANTIC INVARIANT — it MUST appear in every generated image of that character without exception. Be specific, concrete, and immutable. Never use vague terms like "attractive" or "beautiful".

You will output ONLY a valid JSON object. No markdown fences, no explanation text outside the JSON."""


def character_ip_architect_user(
    script_content: str,
    character_name_hint: str,
    character_description_hint: str,
    genre: str,
    style: str,
) -> str:
    """Single LLM call handling Script Parser + Character Profiler + ID & Consistency Manager."""
    name_hint = f"User named the main character: \"{character_name_hint}\"." if character_name_hint.strip() else ""
    desc_hint = f"User description hint: \"{character_description_hint}\"." if character_description_hint.strip() else ""
    hints = " ".join(filter(None, [name_hint, desc_hint]))

    return f"""Analyze this video script and extract ALL characters present.
{hints}
Genre: {genre} | Style: {style}

SCRIPT:
---
{script_content[:6000]}
---

Rules:
- Extract the EXACT number of characters in the script — do not invent or omit
- Max 3 characters total (prioritize by screen time if more than 3 exist)
- Supporting characters only if they appear in 2+ scenes with meaningful role
- If user provided name/description hints, apply them to the main character (#CHAR_01)
- If script is narration-only with no people, return empty characters array
- VIS must be a single dense sentence an image model can use directly as a prompt prefix

Return this exact JSON (no markdown, no extra text):
{{
  "characters": [
    {{
      "ref_id": "#CHAR_01",
      "name": "character name from script",
      "role": "main",
      "scene_appearances": [1, 2, 3],
      "physical_dna": {{
        "ethnicity": "specific ethnicity (e.g. Vietnamese, Korean, Black American)",
        "age_range": "exact range like 25-30",
        "gender": "woman/man/non-binary",
        "hair_color": "specific color (e.g. jet black, dark brown with highlights)",
        "hair_style": "specific style (e.g. shoulder-length straight bob)",
        "eye_color": "specific color",
        "skin_tone": "specific tone (e.g. warm medium brown, light olive)",
        "height_build": "specific (e.g. petite, slender, athletic)",
        "distinctive_features": "any unique marks, glasses, mole, scar — or 'none'"
      }},
      "wardrobe_logic": "One sentence: what this character wears and why it fits their role",
      "color_palette": {{
        "primary": "#hexcode",
        "secondary": "#hexcode",
        "accent": "#hexcode",
        "theory_note": "why these colors fit this character"
      }},
      "semantic_invariants": ["feature1", "feature2", "feature3", "feature4"],
      "visual_identity_string": "Complete VIS: [ethnicity] [gender], [age_range], [hair_color] [hair_style] hair, [skin_tone] skin, [distinctive_features if any], [wardrobe summary], [primary_color] dominant palette"
    }}
  ]
}}"""


def build_scene_video_prompt(
    scene_action: str,
    vis_map: dict,
    characters_in_scene: list,
    art_style: str,
) -> str:
    """
    Regional Prompting (Chuẩn 3): dynamically structure prompt based on character count.
    Prevents Color/Feature Bleeding when multiple characters share a frame.

    vis_map: {"#CHAR_01": vis_string, "#CHAR_02": vis_string}
    characters_in_scene: ["#CHAR_01"] or ["#CHAR_01", "#CHAR_02"]
    """
    vises = [vis_map[c] for c in characters_in_scene if c in vis_map]

    if not vises:
        return f"{scene_action}. {art_style}"

    if len(vises) == 1:
        return f"{vises[0]}. Action: {scene_action}. {art_style}"

    if len(vises) == 2:
        return (
            f"Wide shot scene. "
            f"On the left side: {vises[0]}. "
            f"On the right side: {vises[1]}. "
            f"Interaction: {scene_action}. {art_style}"
        )

    return (
        f"Group shot of three people. "
        f"Centered: {vises[0]}. "
        f"To the left: {vises[1]}. "
        f"To the right: {vises[2]}. "
        f"Scene: {scene_action}. {art_style}"
    )


# ── Character design prompt (legacy — kept for fallback) ─────────────────
def character_design_prompt(description: str, style: str, genre: str, variant: int) -> str:
    """Generate ComfyUI/image prompt for character design."""
    style_map = {
        "cinematic": "photorealistic, cinematic lighting, film grain",
        "animation-2d": "2D animation style, flat colors, clean lines",
        "animation-3d": "3D rendered, Pixar style, soft lighting",
        "vlog":      "natural photography, candid, lifestyle",
    }
    style_hint = style_map.get(style, "photorealistic, professional")
    variant_hints = [
        "professional, business casual, confident pose",
        "casual, friendly, warm smile, relaxed",
        "creative, expressive, dynamic pose",
    ]
    return (
        f"portrait of {description}, {variant_hints[variant % 3]}, "
        f"{style_hint}, {genre} aesthetic, "
        f"high quality, detailed, 512x768, centered, white background"
    )


# ── SEO package generation ───────────────────────────────────────────────
SEO_SYSTEM = """Bạn là chuyên gia SEO YouTube với 10 năm kinh nghiệm tăng trưởng kênh.
Nhiệm vụ: tạo gói SEO hoàn chỉnh cho video YouTube.
Trả về JSON hợp lệ."""

def seo_user(
    topic: str,
    genre: str,
    script_summary: str,
    language: str = "vi",
) -> str:
    lang_label = "tiếng Việt" if language == "vi" else "English"
    return f"""Tạo gói SEO YouTube cho video:
- Chủ đề: {topic}
- Thể loại: {genre}
- Nội dung tóm tắt: {script_summary[:500]}
- Ngôn ngữ: {lang_label}

Trả về JSON:
{{
  "title_variants": ["5 tiêu đề khác nhau, tối ưu CTR, dưới 70 ký tự mỗi tiêu đề"],
  "description": "Mô tả đầy đủ SEO (500-800 từ) với timestamps, keywords, hashtags",
  "tags": ["50 tags phù hợp — mix từ rộng và từ hẹp"],
  "thumbnail_prompt": "Prompt tạo thumbnail AI: bold text, bright colors, face expression, high contrast"
}}"""


# ── Quality scoring ──────────────────────────────────────────────────────
QUALITY_SYSTEM = """Bạn là chuyên gia đánh giá chất lượng video YouTube và content viral.
Nhiệm vụ: chấm điểm video dựa trên keyframes và kịch bản.
Trả về JSON hợp lệ."""

QUALITY_USER_TEMPLATE = """Đánh giá chất lượng video YouTube dựa trên {n_frames} keyframes và kịch bản được cung cấp.

Chủ đề: {topic}
Thể loại: {genre}
Script tóm tắt: {script_summary}

Chấm điểm theo thang 100 điểm:
- hook_strength (20đ): Sức hút 3 giây đầu
- story_coherence (20đ): Mạch câu chuyện, logic nội dung
- visual_quality (20đ): Chất lượng hình ảnh, tính nhất quán
- audio_sync (15đ): Chất lượng audio, đồng bộ với video (ước tính)
- character_consistency (10đ): Nhân vật nhất quán xuyên suốt
- pacing (10đ): Nhịp độ, cắt cảnh
- engagement_potential (5đ): Tiềm năng tương tác, share

Trả về JSON:
{{
  "overall_score": 85,
  "hook_strength": 18,
  "story_coherence": 17,
  "visual_quality": 16,
  "audio_sync": 12,
  "character_consistency": 8,
  "pacing": 9,
  "engagement_potential": 5,
  "gpt_feedback": "Nhận xét chi tiết (3-5 câu): điểm mạnh, điểm yếu, đề xuất cải thiện"
}}"""


# ── Cinematic Scene Decomposer ────────────────────────────────────────────
CINEMATIC_DECOMPOSER_SYSTEM = """You are a Senior Cinematic Technical Director specializing in AI video production.
Your task: decompose each scene into production-ready shots for Kling-3-Pro AI video generation.
Each shot must be independently executable and visually coherent in ≤8 seconds.

OUTPUT ONLY valid JSON. No markdown, no explanation outside the JSON.

4-STEP WORKFLOW (execute for every scene):

STEP 1 — Shot Slicing (≤8 seconds per shot)
- Maximum 8 seconds per shot. Each shot has ONE action focus — no multi-action per clip.
- Ensure logical cinematic flow: Establishing Shot → Medium Shot → Close-up.
- If scene duration ≤ 8s: output 1 shot. If 9-16s: 2 shots. If 17-24s: 3 shots.

STEP 2 — Character Consistency (Ref ID anchoring)
- Always use the Character Ref ID (#CHAR_01 etc.) in the prompt.
- Repeat core visual traits inline: "[#CHAR_01] Vietnamese man jet black hair scar above left brow..."
- Multi-character spatial anchoring: "left frame", "right frame", "background", "facing each other".

STEP 3 — Production Formula (mandatory prompt structure)
Every prompt must follow: [Style&Mood] + [CameraMove] + [CharacterAction&ID] + [Environment&Lighting] + [MotionIntensity]
Camera terms: dolly zoom, tracking shot, pan, tilt, low-angle, close-up, establishing wide shot.
Lighting terms: volumetric rays, rim light, cinematic lighting, golden hour, neon backlit, practical lights.
Style tokens: cinematic=raw footage 35mm grain; animation-3d=Unreal Engine 5 subsurface scattering; cyberpunk=neon saturation chromatic aberration.

STEP 4 — Self-QC (score before accepting)
Score each shot on: Fidelity(3pts) + Consistency(3pts) + Clarity(2pts) + Feasibility(2pts) = 10pts max.
If score < 8: rewrite the prompt internally until ≥ 8.
If after 2 rewrites still < 8: output with status "REJECTED" (pipeline will use fallback).

GUARDRAILS:
- No generic adjectives: "beautiful", "amazing", "wonderful" — use technical/cinematic terms.
- No outfit changes between shots unless script explicitly states a scene change.
- No physically impossible actions in 8 seconds (no chase + fight + explosion in 1 shot).
- Aspect ratio always 16:9 for cinematic."""


def cinematic_decomposer_user(
    scene_number: int,
    scene_title: str,
    scene_description: str,
    scene_duration_seconds: int,
    scene_video_prompt: str,
    characters_in_scene: list,
    lookbook: dict,
    genre: str,
    style: str,
) -> str:
    """Build user prompt for the Cinematic Scene Decomposer node."""
    # Only include characters actually in this scene
    relevant_lookbook = {
        ref_id: data
        for ref_id, data in lookbook.items()
        if not characters_in_scene or ref_id in characters_in_scene
    }

    lookbook_block = "\n".join(
        f"  {ref_id}: {data.get('key_identifier', data.get('name', ref_id))}"
        for ref_id, data in relevant_lookbook.items()
    ) or "  (no named characters — environmental/narration scene)"

    invariants_block = "\n".join(
        f"  {ref_id}: {', '.join(data.get('constant_elements', []))}"
        for ref_id, data in relevant_lookbook.items()
        if data.get("constant_elements")
    ) or "  (none specified)"

    # Calculate expected shot count for guidance
    expected_shots = max(1, (scene_duration_seconds + 7) // 8)

    return f"""Decompose this scene into {expected_shots} production-ready shot(s):

SCENE {scene_number:02d}: {scene_title}
Total duration: {scene_duration_seconds}s → expect ~{expected_shots} shot(s) of ≤8s
Scene description: {scene_description}
Base video concept (enhance, don't copy verbatim): {scene_video_prompt}
Genre: {genre} | Style: {style} | Aspect ratio: 16:9

CHARACTER VISUAL ANCHORS (embed ref_id + traits in every shot they appear):
{lookbook_block}

CONSTANT ELEMENTS (must appear in every shot containing these characters):
{invariants_block}

Characters in this scene: {characters_in_scene or ['(none — narration/environmental)' ]}

Return JSON:
{{
  "scene_id": "SC{scene_number:02d}",
  "shots": [
    {{
      "shot_id": "SC{scene_number:02d}_SH01",
      "shot_number": 1,
      "duration": 8,
      "prompt": "[Style&Mood], [CameraMove], [CharacterAction with Ref IDs and core traits], [Environment&Lighting], [MotionIntensity]",
      "characters_present": ["#CHAR_01"],
      "qc_score": 8.5,
      "qc_notes": "Brief QC note",
      "status": "APPROVED"
    }}
  ]
}}"""


# ── Sequence Continuity & Motion Coherence Director ───────────────────────────
CONTINUITY_DIRECTOR_SYSTEM = """You are a Sequence Continuity & Motion Coherence Director for an AI video production pipeline.
You receive a full ordered list of APPROVED cinematic shots and must perform four tasks simultaneously across the entire sequence.
Output ONLY a single valid JSON object. No markdown, no explanation outside the JSON.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TASK 1 — BRIDGE LOGIC (Shot-Pair Analysis)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
For every consecutive shot pair (n-1 → n):
- Determine the END STATE of shot n-1: character position (left/center/right frame), facing direction, camera angle, last visible action.
- Write a continuity_notes instruction for shot n that anchors its STARTING FRAME to the end state of n-1.
- 180° Rule: If consecutive shots contain the same characters, verify they stay on the same side of the 180° axis. Flag and correct violations by specifying "match 180° axis from previous shot".
- POV Cut Rule: If shot n-1 ends on a character's eyes or gaze direction, shot n's continuity_notes must specify a POV frame ("POV from #CHAR_01 eyeline — show what they see").
- First shot of sequence: continuity_notes = establish the opening spatial anchor (e.g. "Opening shot. Fade in from black. Establish spatial anchor: #CHAR_01 left frame.").

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TASK 2 — GLOBAL STYLE ANCHOR
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Scan ALL shots as a set:
- Identify the dominant style token (e.g. "cinematic 35mm grain", "neon cyberpunk", "Unreal Engine 5"). Flag any shot whose prompt uses a contradicting style token in continuity_notes.
- Color temperature: shots within the same scene must share a consistent color temperature (warm/cool/neutral). Flag cross-scene mismatches only if jarring.
- Camera vocabulary: within each scene, camera moves must form a coherent grammar. Flag incoherent sequences in continuity_notes.
- Do NOT rewrite prompts — only write continuity_notes that address issues found.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TASK 3 — AUDIO BLUEPRINT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
For every shot, produce:
- sfx_prompt: Specific Foley sounds for this exact 8-second clip. Be concrete and physical: "heavy leather boots on wet cobblestone, distant crowd murmur, wind through pine trees". Never vague ("action sounds", "background noise").
- ambience: Environmental background layer in ≤ 500 characters: "Rainy alleyway, neon city district, distant traffic hum, occasional police siren two blocks away."
- sfx_prompt and ambience must be consistent within the same scene location. If characters move environments mid-sequence, transition the audio accordingly.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TASK 4 — MOTION VECTOR & PACING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
For every shot, assign motion_intensity (integer 0-10):
  0-1 = locked camera, completely static scene (title card, still portrait)
  2-3 = subtle movement (gentle push-in, slow pan, character breathes)
  4-5 = moderate action (walking, slow camera track, mid-paced dialogue)
  6-7 = active scene (running, fast pan, chase begins, handheld)
  8-9 = high intensity (fight, rapid cutting, shaky cam, explosion proximity)
  10  = maximum chaos (full sprint chase, handheld running, debris flying)
Pacing logic: motion_intensity values across the sequence must tell a coherent story arc. Flag anomalies (e.g. intensity 9 surrounded by intensity 2 with no narrative reason) in continuity_notes.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT SCHEMA (return exactly this, nothing else):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{
  "sequence_id": "SEQ_001_<project_uuid>",
  "total_duration": "<Ns>",
  "motion_intensity_avg": <float 0-10, mean across all shots rounded to 1 decimal>,
  "workflow_steps": [
    {
      "clip_id": "<shot_id e.g. SC01_SH01>",
      "video_prompt": "[CONTINUITY: <one instruction line, max 20 words>]",
      "continuity_notes": "<bridge logic + style anchor notes for this shot>",
      "sfx_prompt": "<specific Foley sounds>",
      "ambience": "<environmental background ≤300 chars>",
      "motion_intensity": <integer 0-10>
    }
  ]
}

GUARDRAILS:
- video_prompt must contain ONLY the [CONTINUITY: ...] prefix tag — do NOT repeat or copy the original prompt. The system will prepend it automatically.
- [CONTINUITY: ...] tag must be under 20 words total (everything inside the brackets).
- continuity_notes for shot n must reference the previous shot_id by name (e.g. "Match #CHAR_01 position from SC01_SH01.").
- Never invent characters not present in characters_present.
- motion_intensity must be an integer, never a float.
- ambience must be ≤ 500 characters.
- If two shots share the same scene_id prefix (SC01), their sfx/ambience should be variations of the same environment unless the script requires a location change."""


def continuity_director_user(
    shots: list[dict],
    lookbook: dict,
    genre: str,
    style: str,
    project_id: str,
) -> str:
    """Build the user prompt for the Continuity Director — full sequence context."""
    total_duration = sum(s.get("duration", 8) for s in shots)

    shots_block = ""
    for i, s in enumerate(shots):
        shots_block += (
            f"\n[SHOT {i + 1}] {s.get('shot_id', f'SHOT_{i + 1}')}\n"
            f"  Scene: {s.get('scene_id', 'unknown')}\n"
            f"  Duration: {s.get('duration', 8)}s\n"
            f"  Characters: {s.get('characters_present', [])}\n"
            f"  Prompt: {s.get('prompt', '')}\n"
        )

    char_block = ""
    for ref_id, data in lookbook.items():
        char_block += (
            f"  {ref_id} ({data.get('name', ref_id)}): "
            f"{data.get('key_identifier', '')} | "
            f"constant: {', '.join(data.get('constant_elements', []))}\n"
        )
    if not char_block:
        char_block = "  (no named characters — narration/environmental sequence)\n"

    return f"""Analyze this complete shot sequence and produce the Master Render List.

PROJECT: {project_id}
GENRE: {genre} | STYLE: {style}
TOTAL SHOTS: {len(shots)} | TOTAL DURATION: {total_duration}s

CHARACTER LOOKBOOK (spatial/visual anchors for continuity):
{char_block}
ORDERED SHOT SEQUENCE:
{shots_block}
Instructions:
1. Process ALL {len(shots)} shots — do not skip any.
2. workflow_steps array must have exactly {len(shots)} entries, in the same order.
3. Each clip_id must exactly match the shot_id field shown above.
4. sequence_id = "SEQ_001_{project_id}"
5. total_duration = "{total_duration}s"
6. Compute motion_intensity_avg as arithmetic mean of all motion_intensity values, rounded to 1 decimal.

Return ONLY the JSON object. No preamble, no explanation."""


# ── SEO A/B Agent ─────────────────────────────────────────────────────────────
SEO_AB_SYSTEM = """You are a YouTube Growth Expert & Viral Content Strategist.
Given a video project (script summary, genre, topic, characters), generate TWO distinct SEO packages for A/B testing.

Package A = SEO-optimized (keyword-first, searchable, long-tail)
Package B = Viral/Clickbait (curiosity gap, emotion hook, trending phrasing)

Each package must contain:
- title_seo: Keyword-first title, ≤70 chars (starts with main keyword)
- title_clickbait: Emotion/curiosity hook title, ≤70 chars
- title_story: Narrative/storytelling title, ≤70 chars
- description: 4-section structure:
    Line 1-2: HOOK (strong emotion/curiosity opener)
    Section 2: Summary (2-3 sentences what the video is about)
    Section 3: Timestamps (00:00 Intro, estimate timestamps from scene structure)
    Section 4: CTA + 10 relevant hashtags
- tags: List of exactly 20 tags (broad → narrow, mix Vietnamese + English)
- thumbnail_prompt: One sentence describing a 16:9 still image — focus on character closeup with Ref ID if available, dramatic lighting, space for text overlay. NO text in the image itself.
- filename: SEO-friendly filename in Vietnamese without diacritics, kebab-case, no special chars (e.g., "bi-mat-nhan-vat-ai-concept.mp4")

Output ONLY valid JSON, exactly this structure:
{
  "package_a": {
    "title_seo": "...",
    "title_clickbait": "...",
    "title_story": "...",
    "description": "...",
    "tags": ["tag1", "tag2", ...],
    "thumbnail_prompt": "...",
    "filename": "..."
  },
  "package_b": {
    "title_seo": "...",
    "title_clickbait": "...",
    "title_story": "...",
    "description": "...",
    "tags": ["tag1", "tag2", ...],
    "thumbnail_prompt": "...",
    "filename": "..."
  }
}
No markdown, no explanation outside JSON."""


def seo_ab_user(
    topic: str,
    genre: str,
    style: str,
    script_summary: str,
    language: str,
    character_names: list[str],
    total_duration_s: int,
) -> str:
    """Build user prompt for SEO A/B agent."""
    lang_label = "Tiếng Việt" if language == "vi" else "English"
    char_block = ", ".join(character_names) if character_names else "(no named characters)"
    return f"""Generate 2 SEO packages (A/B) for this video:

TOPIC: {topic}
GENRE: {genre} | STYLE: {style}
LANGUAGE: {lang_label}
DURATION: ~{total_duration_s}s
CHARACTERS: {char_block}

SCRIPT SUMMARY (first 500 chars):
{script_summary[:500]}

Requirements:
- All titles, descriptions, and tags in {lang_label}
- Tags: mix broad (genre keywords) → specific (topic keywords)
- thumbnail_prompt: use character Ref ID if available (e.g., "#CHAR_01 closeup")
- filename: no diacritics, kebab-case, no spaces, end with .mp4
- description timestamps should estimate based on ~{total_duration_s // 3}s scenes

Return ONLY the JSON object."""
