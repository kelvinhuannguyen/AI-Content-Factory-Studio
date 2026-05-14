import Link from "next/link";
import {
  Video, Music, Film, ArrowRight, Sparkles,
  Plus, TrendingUp, Clock, CheckCircle, Smartphone, Monitor,
} from "lucide-react";
import { DashboardClient } from "./DashboardClient";

const PRODUCTION_MODES = [
  {
    href: "/create/short",
    icon: Video,
    metaIcon: Smartphone,
    title: "Video ngắn",
    subtitle: "Reels · Shorts · TikTok",
    meta: "15s – 3 phút · 9:16",
    gradient: "from-orange-500 to-amber-500",
    glowClass: "dark:shadow-[0_0_16px_rgba(255,122,50,0.35)]",
    tag: "Phổ biến",
  },
  {
    href: "/create/long",
    icon: Film,
    metaIcon: Monitor,
    title: "Video dài",
    subtitle: "YouTube · Documentary",
    meta: "5 phút – 3 giờ · 16:9",
    gradient: "from-teal-500 to-cyan-500",
    glowClass: "dark:shadow-[0_0_16px_rgba(20,228,212,0.35)]",
    tag: "YouTube",
  },
  {
    href: "/create/music-mv",
    icon: Music,
    metaIcon: Monitor,
    title: "MV ca nhạc",
    subtitle: "Music Video · Suno AI",
    meta: "Không giới hạn · 16:9 / 9:16",
    gradient: "from-pink-500 to-rose-500",
    glowClass: "dark:shadow-[0_0_16px_rgba(236,72,153,0.35)]",
    tag: "Nhạc AI",
  },
];

export default function DashboardPage() {
  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Xin chào 👋</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Chọn loại nội dung bạn muốn sản xuất hôm nay
        </p>
      </div>

      {/* Quick-start cards */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {PRODUCTION_MODES.map(({ href, icon: Icon, metaIcon: MetaIcon, title, subtitle, meta, gradient, glowClass, tag }) => (
          <Link
            key={href}
            href={href}
            className="group flex items-center gap-4 rounded-2xl bg-card border border-border/50 card-shadow px-4 py-3.5 transition-all duration-200 hover:card-shadow-md hover:-translate-y-0.5 dark:glass glow-hover"
          >
            <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br ${gradient} ${glowClass}`}>
              <Icon className="h-5 w-5 text-white" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <p className="text-sm font-semibold text-foreground truncate">{title}</p>
                <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">{tag}</span>
              </div>
              <p className="text-xs text-muted-foreground truncate">{subtitle}</p>
              <div className="mt-0.5 flex items-center gap-1">
                <MetaIcon className="h-2.5 w-2.5 text-muted-foreground/60" />
                <span className="text-[10px] text-muted-foreground/80">{meta}</span>
              </div>
            </div>
            <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground/40 transition-transform duration-150 group-hover:translate-x-0.5 group-hover:text-primary" />
          </Link>
        ))}
      </div>

      {/* Client component: stats + recent projects from API */}
      <DashboardClient />
    </div>
  );
}
