"use client";

import Link from "next/link";
import {
  ArrowLeft, Video, Film, Music, AlertCircle,
  Clock, CheckCircle, XCircle, Play, RotateCcw,
  FileText, Users, Clapperboard, Zap, Star, Search, Youtube
} from "lucide-react";
import { useProject } from "@/hooks/useProject";
import { PRODUCTION_TYPE_LABELS, STATUS_LABELS } from "@/lib/constants";
import { formatDate } from "@/lib/utils";
import type { ProjectStatus } from "@/types/project";

const TYPE_ICON = { short_video: Video, long_video: Film, music_mv: Music };
const TYPE_GRADIENT: Record<string, string> = {
  short_video: "from-violet-500 to-purple-700",
  long_video:  "from-blue-500 to-indigo-700",
  music_mv:    "from-pink-500 to-rose-700",
};

// Map status → wizard URL to resume
const STATUS_STEP: Partial<Record<ProjectStatus, string>> = {
  draft:            "topic",
  topic_selected:   "script",
  script_ready:     "config",
  config_done:      "character",
  character_selected: "scenes",
  scenes_ready:     "generate",
  generating:       "generate",
  assembly:         "generate",
  quality_review:   "review",
  human_review:     "review",
  seo_ready:        "seo",
  seo_approved:     "publish",
};

const PIPELINE_STEPS = [
  { id: "topic",     icon: Search,       label: "Chủ đề",       statuses: ["topic_selected"] },
  { id: "script",    icon: FileText,     label: "Kịch bản",     statuses: ["script_ready"] },
  { id: "config",    icon: Clapperboard, label: "Cấu hình",     statuses: ["config_done"] },
  { id: "character", icon: Users,        label: "Nhân vật",     statuses: ["character_selected"] },
  { id: "scenes",    icon: Play,         label: "Phân cảnh",    statuses: ["scenes_ready"] },
  { id: "generate",  icon: Zap,          label: "Tạo media",    statuses: ["generating", "assembly"] },
  { id: "review",    icon: Star,         label: "Duyệt",        statuses: ["quality_review", "human_review"] },
  { id: "seo",       icon: Search,       label: "SEO",          statuses: ["seo_ready", "seo_approved"] },
  { id: "publish",   icon: Youtube,      label: "Đăng bài",     statuses: ["publishing", "published"] },
];

const STATUS_ICON: Record<string, React.ReactNode> = {
  done:    <CheckCircle className="h-4 w-4 text-emerald-500" />,
  active:  <Clock className="h-4 w-4 text-amber-500 animate-pulse" />,
  pending: <div className="h-4 w-4 rounded-full border-2 border-border" />,
  failed:  <XCircle className="h-4 w-4 text-destructive" />,
};

function getStepState(stepStatuses: string[], projectStatus: string): "done" | "active" | "pending" | "failed" {
  if (projectStatus === "failed") return "failed";
  const order = PIPELINE_STEPS.flatMap((s) => s.statuses);
  const currentIdx = order.indexOf(projectStatus);
  const stepIdx = Math.max(...stepStatuses.map((s) => order.indexOf(s)));
  if (stepIdx < 0) return "pending";
  if (currentIdx > stepIdx) return "done";
  if (stepStatuses.includes(projectStatus)) return "active";
  return "pending";
}

export default function ProjectDetailPage({ params }: { params: { id: string } }) {
  const { id } = params;
  const { project, isLoading, error, mutate } = useProject(id);

  if (isLoading) {
    return (
      <div className="space-y-6 animate-fade-in">
        <div className="h-8 w-48 rounded-xl bg-muted animate-pulse" />
        <div className="h-48 rounded-2xl bg-muted animate-pulse" />
        <div className="h-64 rounded-2xl bg-muted animate-pulse" />
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="flex flex-col items-center gap-4 py-20">
        <AlertCircle className="h-10 w-10 text-destructive/60" />
        <p className="text-muted-foreground">Không tìm thấy dự án</p>
        <Link href="/projects" className="text-primary hover:underline text-sm">← Quay lại danh sách</Link>
      </div>
    );
  }

  const Icon     = TYPE_ICON[project.production_type] ?? Video;
  const gradient = TYPE_GRADIENT[project.production_type] ?? "from-violet-500 to-purple-700";
  const resumeStep = STATUS_STEP[project.status] ?? "topic";
  const wizardType = project.production_type === "short_video" ? "short"
                   : project.production_type === "long_video"  ? "long"
                   : "music-mv";
  const resumeUrl = `/create/${wizardType}`;

  return (
    <div className="mx-auto max-w-3xl space-y-6 animate-fade-in">
      {/* Back */}
      <Link href="/projects" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors">
        <ArrowLeft className="h-4 w-4" /> Danh sách dự án
      </Link>

      {/* Hero card */}
      <div className="overflow-hidden rounded-2xl bg-card border border-border/50 card-shadow">
        <div className={`h-2 w-full bg-gradient-to-r ${gradient}`} />
        <div className="p-5">
          <div className="flex items-start gap-4">
            <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br ${gradient}`}>
              <Icon className="h-6 w-6 text-white" />
            </div>
            <div className="min-w-0 flex-1">
              <h1 className="text-xl font-bold text-foreground truncate">{project.title}</h1>
              <div className="mt-1 flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
                <span>{PRODUCTION_TYPE_LABELS[project.production_type]}</span>
                {project.genre    && <span>· {project.genre}</span>}
                {project.style    && <span>· {project.style}</span>}
                {project.duration_seconds && (
                  <span>· {project.duration_seconds < 60
                    ? `${project.duration_seconds}s`
                    : `${Math.round(project.duration_seconds / 60)} phút`}
                  </span>
                )}
              </div>
              {project.topic && (
                <p className="mt-2 text-sm text-muted-foreground line-clamp-2 leading-relaxed">
                  {project.topic}
                </p>
              )}
            </div>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-3">
            <span className={`rounded-full px-3 py-1 text-xs font-semibold ${
              project.status === "published" ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300"
              : project.status === "failed"  ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300"
              : "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300"
            }`}>
              {STATUS_LABELS[project.status] ?? project.status}
            </span>
            <span className="text-xs text-muted-foreground">Cập nhật {formatDate(project.updated_at)}</span>
          </div>

          {project.status !== "published" && project.status !== "failed" && (
            <div className="mt-4 flex gap-2">
              <Link
                href={resumeUrl}
                className="flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 transition-colors"
              >
                <Play className="h-4 w-4" /> Tiếp tục sản xuất
              </Link>
              <button
                onClick={() => mutate()}
                className="flex items-center gap-2 rounded-xl border border-border px-3 py-2 text-sm hover:bg-muted transition-colors"
              >
                <RotateCcw className="h-4 w-4" />
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Pipeline progress */}
      <div className="rounded-2xl bg-card border border-border/50 card-shadow overflow-hidden">
        <div className="px-5 py-4 border-b border-border/60">
          <h2 className="text-sm font-semibold">Tiến trình sản xuất</h2>
        </div>
        <div className="p-5">
          <div className="space-y-3">
            {PIPELINE_STEPS.map((step, idx) => {
              const state = getStepState(step.statuses, project.status);
              const StepIcon = step.icon;
              return (
                <div key={step.id} className="flex items-center gap-4">
                  {/* Connector line */}
                  <div className="relative flex flex-col items-center">
                    <div className={`flex h-8 w-8 items-center justify-center rounded-xl ${
                      state === "done"   ? "bg-emerald-50 dark:bg-emerald-900/20"
                      : state === "active" ? "bg-amber-50 dark:bg-amber-900/20"
                      : "bg-muted"
                    }`}>
                      <StepIcon className={`h-4 w-4 ${
                        state === "done"   ? "text-emerald-500"
                        : state === "active" ? "text-amber-500"
                        : "text-muted-foreground/40"
                      }`} />
                    </div>
                    {idx < PIPELINE_STEPS.length - 1 && (
                      <div className={`absolute top-8 h-3 w-px ${state === "done" ? "bg-emerald-200 dark:bg-emerald-800" : "bg-border"}`} />
                    )}
                  </div>
                  <div className="flex-1 pb-3">
                    <div className="flex items-center gap-2">
                      <span className={`text-sm font-medium ${state === "pending" ? "text-muted-foreground" : "text-foreground"}`}>
                        {step.label}
                      </span>
                      {STATUS_ICON[state]}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
