import Link from "next/link";
import { Video, Film, Music, ArrowRight, Smartphone, Monitor } from "lucide-react";

const MODES = [
  {
    href: "/create/short",
    icon: Video,
    ratioIcon: Smartphone,
    title: "Video ngắn",
    subtitle: "Reels · YouTube Shorts · TikTok",
    description: "Sản xuất video dọc tối ưu cho mạng xã hội. AI nghiên cứu xu hướng, viết kịch bản, tạo nhân vật và dựng video hoàn chỉnh.",
    durations: "15s · 30s · 60s · 90s · 2p · 3p",
    ratio: "9:16 · Dọc",
    gradient: "from-violet-500 to-purple-700",
    tag: "Phổ biến nhất",
    tagColor: "bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300",
  },
  {
    href: "/create/long",
    icon: Film,
    ratioIcon: Monitor,
    title: "Video dài",
    subtitle: "YouTube · Documentary · Tutorial",
    description: "Tạo nội dung YouTube chất lượng cao. Kịch bản chuẩn Hollywood, thiết kế nhân vật nhất quán xuyên suốt video.",
    durations: "5 phút → 3 giờ",
    ratio: "16:9 · Ngang",
    gradient: "from-blue-500 to-indigo-700",
    tag: "YouTube",
    tagColor: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  },
  {
    href: "/create/music-mv",
    icon: Music,
    ratioIcon: Monitor,
    title: "MV ca nhạc",
    subtitle: "Music Video · Suno AI",
    description: "Music Video hoàn chỉnh với âm nhạc Suno AI. Hỗ trợ 17 thể loại từ Pop đến Thánh ca. Không giới hạn thời lượng.",
    durations: "Không giới hạn",
    ratio: "16:9 / 9:16",
    gradient: "from-pink-500 to-rose-700",
    tag: "Có nhạc AI",
    tagColor: "bg-pink-100 text-pink-700 dark:bg-pink-900/40 dark:text-pink-300",
  },
];

export default function CreatePage() {
  return (
    <div className="mx-auto max-w-3xl space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Tạo nội dung mới</h1>
        <p className="mt-1 text-sm text-muted-foreground">Chọn loại sản xuất để bắt đầu quy trình AI</p>
      </div>

      <div className="space-y-3">
        {MODES.map(({ href, icon: Icon, ratioIcon: RatioIcon, title, subtitle, description, durations, ratio, gradient, tag, tagColor }) => (
          <Link
            key={href}
            href={href}
            className="group flex items-center gap-5 rounded-2xl bg-card border border-border/50 card-shadow p-4 transition-all duration-200 hover:card-shadow-md hover:-translate-y-0.5"
          >
            {/* Icon */}
            <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br ${gradient}`}>
              <Icon className="h-6 w-6 text-white" />
            </div>

            {/* Content */}
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-base font-semibold text-foreground">{title}</span>
                <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${tagColor}`}>{tag}</span>
              </div>
              <p className="text-xs text-primary font-medium mt-0.5">{subtitle}</p>
              <p className="mt-1.5 text-xs text-muted-foreground leading-relaxed max-w-xl">{description}</p>
              <div className="mt-2 flex flex-wrap items-center gap-3">
                <span className="flex items-center gap-1 rounded-lg bg-muted px-2.5 py-1 text-[11px] font-medium text-muted-foreground">
                  ⏱ {durations}
                </span>
                <span className="flex items-center gap-1 rounded-lg bg-muted px-2.5 py-1 text-[11px] font-medium text-muted-foreground">
                  <RatioIcon className="h-3 w-3" /> {ratio}
                </span>
              </div>
            </div>

            {/* Arrow */}
            <ArrowRight className="h-5 w-5 shrink-0 text-muted-foreground/30 transition-transform duration-150 group-hover:translate-x-0.5 group-hover:text-primary" />
          </Link>
        ))}
      </div>

      {/* Aspect ratio note — compact */}
      <div className="rounded-xl border border-border/40 bg-muted/40 px-4 py-3">
        <p className="text-xs text-muted-foreground">
          <span className="font-semibold text-foreground">📐 Tỉ lệ màn hình tự động:</span>
          {" "}Video ngắn → <strong>9:16 dọc</strong> (TikTok/Reels/Shorts)
          {" · "}Video dài → <strong>16:9 ngang</strong> (YouTube)
          {" · "}MV → 16:9 mặc định, có thể đổi 9:16
        </p>
      </div>
    </div>
  );
}
