// ── Video genres ────────────────────────────────────────────────────────
export const VIDEO_GENRES = [
  { value: "drama", label: "Kịch tính" },
  { value: "comedy", label: "Hài hước" },
  { value: "thriller", label: "Kinh dị tâm lý" },
  { value: "horror", label: "Kinh dị" },
  { value: "romance", label: "Lãng mạn" },
  { value: "action", label: "Hành động" },
  { value: "sci-fi", label: "Khoa học viễn tưởng" },
  { value: "fantasy", label: "Huyền ảo" },
  { value: "mystery", label: "Bí ẩn" },
  { value: "documentary", label: "Phóng sự" },
  { value: "educational", label: "Giáo dục / Tutorial" },
  { value: "vlog", label: "Vlog" },
  { value: "travel", label: "Du lịch" },
  { value: "food", label: "Ẩm thực / Nấu ăn" },
  { value: "tech-review", label: "Review công nghệ" },
  { value: "product-review", label: "Review sản phẩm" },
  { value: "news", label: "Tin tức / Bình luận" },
  { value: "motivational", label: "Truyền cảm hứng" },
  { value: "true-crime", label: "Tội phạm có thật" },
  { value: "sports", label: "Thể thao" },
  { value: "gaming", label: "Gaming" },
  { value: "fashion", label: "Thời trang / Làm đẹp" },
  { value: "fitness", label: "Fitness" },
  { value: "business", label: "Kinh doanh / Tài chính" },
  { value: "lifestyle", label: "Lifestyle" },
  { value: "reaction", label: "Reaction" },
  { value: "challenge", label: "Challenge" },
] as const;

// ── Video styles ─────────────────────────────────────────────────────────
export const VIDEO_STYLES = [
  { value: "cinematic", label: "Điện ảnh (Hollywood)" },
  { value: "vlog", label: "Vlog (tự nhiên)" },
  { value: "documentary", label: "Phóng sự" },
  { value: "animation-2d", label: "Hoạt hình 2D" },
  { value: "animation-3d", label: "Hoạt hình 3D" },
  { value: "educational", label: "Giáo dục (bảng trắng)" },
  { value: "talking-head", label: "Talking Head" },
  { value: "b-roll", label: "B-Roll / Montage" },
  { value: "slideshow", label: "Slideshow" },
] as const;

// ── Music MV genres ──────────────────────────────────────────────────────
export const MUSIC_GENRES = [
  { value: "pop", label: "Pop" },
  { value: "rock", label: "Rock" },
  { value: "hip-hop", label: "Hip-Hop / Rap" },
  { value: "rnb", label: "R&B / Soul" },
  { value: "edm", label: "EDM / Electronic" },
  { value: "ballad", label: "Ballad" },
  { value: "indie", label: "Indie" },
  { value: "jazz", label: "Jazz" },
  { value: "classical", label: "Classical" },
  { value: "lofi", label: "Lofi" },
  { value: "kpop", label: "K-pop style" },
  { value: "folk", label: "Dân ca" },
  { value: "country", label: "Country" },
  { value: "reggae", label: "Reggae" },
  { value: "metal", label: "Metal" },
  { value: "gospel", label: "Thánh ca (Gospel / Hymn)" },
  { value: "other", label: "Thể loại khác" },
] as const;

// ── Duration options ─────────────────────────────────────────────────────
export const SHORT_DURATIONS = [
  { value: 15,  label: "15 giây" },
  { value: 30,  label: "30 giây" },
  { value: 60,  label: "1 phút" },
  { value: 90,  label: "1.5 phút" },
  { value: 120, label: "2 phút" },
  { value: 180, label: "3 phút" },
];

export const LONG_DURATIONS = [
  { value: 300,   label: "5 phút" },
  { value: 600,   label: "10 phút" },
  { value: 900,   label: "15 phút" },
  { value: 1800,  label: "30 phút" },
  { value: 3600,  label: "1 giờ" },
  { value: 5400,  label: "1.5 giờ" },
  { value: 7200,  label: "2 giờ" },
  { value: 10800, label: "3 giờ" },
];

// ── Aspect ratio — tự động theo loại sản xuất (không cần người dùng chọn)
// Short video (Reels/Shorts/TikTok) → 9:16 dọc
// Long video (YouTube)              → 16:9 ngang
// MV ca nhạc                        → 16:9 mặc định (YouTube MV), có thể đổi 9:16
export const ASPECT_RATIOS = {
  short_video: { ratio: "9:16",  label: "9:16 dọc",   css: "aspect-[9/16]",  note: "Chuẩn TikTok · Reels · Shorts" },
  long_video:  { ratio: "16:9",  label: "16:9 ngang", css: "aspect-video",   note: "Chuẩn YouTube" },
  music_mv:    { ratio: "16:9",  label: "16:9 ngang", css: "aspect-video",   note: "Chuẩn YouTube MV" },
} as const;

export const MV_ASPECT_OPTIONS = [
  { value: "16:9", label: "16:9 ngang", note: "YouTube MV (phổ biến hơn)" },
  { value: "9:16", label: "9:16 dọc",   note: "Shorts / Reels MV" },
] as const;

// ── Wizard steps ─────────────────────────────────────────────────────────
export const SHORT_VIDEO_STEPS = [
  { id: "topic",     label: "Chủ đề" },
  { id: "config",    label: "Cấu hình" },
  { id: "script",    label: "Kịch bản" },
  { id: "character", label: "Nhân vật" },
  { id: "scenes",    label: "Phân cảnh" },
  { id: "generate",  label: "Tạo media" },
  { id: "review",    label: "Duyệt" },
  { id: "seo",       label: "SEO" },
  { id: "publish",   label: "Đăng bài" },
];

export const LONG_VIDEO_STEPS = SHORT_VIDEO_STEPS;

export const MUSIC_MV_STEPS = [
  { id: "topic", label: "Chủ đề" },
  { id: "script", label: "Kịch bản" },
  { id: "music", label: "Âm nhạc" },
  { id: "config", label: "Cấu hình" },
  { id: "character", label: "Nhân vật" },
  { id: "scenes", label: "Phân cảnh" },
  { id: "generate", label: "Tạo media" },
  { id: "review", label: "Duyệt" },
  { id: "seo", label: "SEO" },
  { id: "publish", label: "Đăng bài" },
];

// ── Status labels ────────────────────────────────────────────────────────
export const STATUS_LABELS: Record<string, string> = {
  draft: "Nháp",
  topic_selected: "Đã chọn chủ đề",
  script_ready: "Kịch bản xong",
  config_done: "Đã cấu hình",
  character_selected: "Nhân vật xong",
  scenes_ready: "Phân cảnh xong",
  generating: "Đang tạo media",
  assembly: "Đang dựng video",
  quality_review: "Chấm điểm chất lượng",
  human_review: "Chờ duyệt",
  seo_ready: "SEO xong",
  seo_approved: "SEO đã duyệt",
  publishing: "Đang đăng",
  published: "Đã đăng",
  failed: "Lỗi",
};

export const PRODUCTION_TYPE_LABELS: Record<string, string> = {
  short_video: "Video ngắn",
  long_video: "Video dài",
  music_mv: "MV ca nhạc",
};
