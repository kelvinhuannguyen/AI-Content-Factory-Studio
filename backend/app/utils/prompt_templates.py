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
{script_content[:3000]}
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
