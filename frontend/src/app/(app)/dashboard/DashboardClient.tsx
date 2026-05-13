"use client";

import Link from "next/link";
import { Plus, Sparkles, CheckCircle, Clock, TrendingUp, Video, Film, Music, AlertCircle, RefreshCw } from "lucide-react";
import { useProjects } from "@/hooks/useProject";
import { PRODUCTION_TYPE_LABELS, STATUS_LABELS } from "@/lib/constants";
import { formatDate } from "@/lib/utils";
import type { Project } from "@/types/project";

const STATUS_COLOR: Record<string, string> = {
  draft:            "bg-muted text-muted-foreground",
  topic_selected:   "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
  script_ready:     "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300",
  config_done:      "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300",
  character_selected: "bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300",
  scenes_ready:     "bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-300",
  generating:       "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
  assembly:         "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300",
  quality_review:   "bg-pink-100 text-pink-700 dark:bg-pink-900/30 dark:text-pink-300",
  human_review:     "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300",
  seo_ready:        "bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-300",
  seo_approved:     "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
  publishing:       "bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300",
  published:        "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300",
  failed:           "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300",
};

const TYPE_ICON = {
  short_video: Video,
  long_video: Film,
  music_mv: Music,
};

function ProjectRow({ project }: { project: Project }) {
  const Icon = TYPE_ICON[project.production_type] ?? Video;
  return (
    <Link
      href={`/projects/${project.id}`}
      className="group flex items-center gap-4 px-5 py-3.5 hover:bg-muted/40 transition-colors"
    >
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted">
        <Icon className="h-4 w-4 text-muted-foreground" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-foreground truncate group-hover:text-primary transition-colors">
          {project.title}
        </p>
        <p className="text-xs text-muted-foreground">
          {PRODUCTION_TYPE_LABELS[project.production_type]} · {formatDate(project.updated_at)}
        </p>
      </div>
      <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-[11px] font-medium ${STATUS_COLOR[project.status] ?? "bg-muted text-muted-foreground"}`}>
        {STATUS_LABELS[project.status] ?? project.status}
      </span>
    </Link>
  );
}

export function DashboardClient() {
  const { data, isLoading, error, mutate } = useProjects(1, 6);

  const total     = data?.total ?? 0;
  const published = data?.items.filter((p) => p.status === "published").length ?? 0;
  const inProgress = data?.items.filter(
    (p) => !["draft", "published", "failed"].includes(p.status)
  ).length ?? 0;

  const STATS = [
    { label: "Tổng dự án",  value: total,      icon: Sparkles,     color: "text-violet-500" },
    { label: "Đã xuất bản", value: published,   icon: CheckCircle,  color: "text-emerald-500" },
    { label: "Đang xử lý",  value: inProgress,  icon: Clock,        color: "text-amber-500" },
    { label: "Xu hướng",    value: 0,            icon: TrendingUp,   color: "text-blue-500" },
  ];

  return (
    <>
      {/* Stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {STATS.map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="rounded-2xl bg-card border border-border/50 card-shadow px-4 py-3.5">
            <div className="flex items-center justify-between">
              <p className="text-xl font-bold text-foreground">{isLoading ? "—" : value}</p>
              <Icon className={`h-4 w-4 ${color}`} />
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{label}</p>
          </div>
        ))}
      </div>

      {/* Recent projects */}
      <div className="rounded-2xl bg-card border border-border/50 card-shadow overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-border/60">
          <h2 className="text-sm font-semibold">Dự án gần đây</h2>
          <div className="flex items-center gap-3">
            <button
              onClick={() => mutate()}
              className="text-muted-foreground hover:text-foreground transition-colors"
              title="Làm mới"
            >
              <RefreshCw className="h-3.5 w-3.5" />
            </button>
            <Link href="/projects" className="text-xs text-primary hover:underline font-medium">
              Xem tất cả
            </Link>
          </div>
        </div>

        {isLoading && (
          <div className="space-y-px divide-y divide-border/40">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="flex items-center gap-4 px-5 py-3.5">
                <div className="h-8 w-8 rounded-lg bg-muted animate-pulse" />
                <div className="flex-1 space-y-2">
                  <div className="h-3 w-2/3 rounded bg-muted animate-pulse" />
                  <div className="h-2.5 w-1/3 rounded bg-muted animate-pulse" />
                </div>
                <div className="h-5 w-16 rounded-full bg-muted animate-pulse" />
              </div>
            ))}
          </div>
        )}

        {error && (
          <div className="flex flex-col items-center gap-2 py-10 text-center">
            <AlertCircle className="h-6 w-6 text-destructive/60" />
            <p className="text-sm text-muted-foreground">Không kết nối được backend</p>
            <button onClick={() => mutate()} className="text-xs text-primary hover:underline">Thử lại</button>
          </div>
        )}

        {!isLoading && !error && data?.items.length === 0 && (
          <div className="flex flex-col items-center justify-center gap-3 py-12 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-muted">
              <Sparkles className="h-5 w-5 text-muted-foreground/50" />
            </div>
            <div>
              <p className="text-sm font-medium text-foreground">Chưa có dự án nào</p>
              <p className="mt-0.5 text-xs text-muted-foreground">Bắt đầu tạo video AI đầu tiên</p>
            </div>
            <Link
              href="/create"
              className="flex items-center gap-1.5 rounded-xl bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              <Plus className="h-3.5 w-3.5" /> Tạo dự án đầu tiên
            </Link>
          </div>
        )}

        {!isLoading && !error && data && data.items.length > 0 && (
          <div className="divide-y divide-border/40">
            {data.items.map((p) => <ProjectRow key={p.id} project={p} />)}
          </div>
        )}
      </div>
    </>
  );
}
