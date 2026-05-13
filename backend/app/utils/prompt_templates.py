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
SCENE_PROMPT_SYSTEM = """Bạn là chuyên gia tạo prompt cho AI video generation (Seedance, Kling AI, RunwayML).
Nhiệm vụ: chuyển đổi mô tả cảnh quay thành video prompt tối ưu cho AI.
Trả về JSON hợp lệ."""

def scene_prompt_user(
    scene_title: str,
    shot_description: str,
    narration: str,
    character_description: str,
    genre: str,
    style: str,
    production_type: str,
) -> str:
    aspect = "9:16 vertical" if production_type == "short_video" else "16:9 widescreen"
    return f"""Tạo video prompt cho AI video generation từ cảnh sau:
- Cảnh: {scene_title}
- Mô tả: {shot_description}
- Narration: {narration}
- Nhân vật: {character_description}
- Thể loại: {genre} | Phong cách: {style} | Tỉ lệ: {aspect}

Trả về JSON:
{{
  "video_prompt": "Prompt tiếng Anh chi tiết cho Seedance/Kling, bao gồm: subject, action, environment, camera movement, lighting, mood, style. Tối thiểu 50 từ.",
  "negative_prompt": "Những gì cần tránh (blur, watermark, text, ugly, deformed...)"
}}"""


# ── Character design prompt ──────────────────────────────────────────────
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
