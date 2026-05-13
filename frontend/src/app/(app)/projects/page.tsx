"use client";

import Link from "next/link";
import { Plus, Video, Film, Music, Search, RefreshCw, AlertCircle } from "lucide-react";
import { useState } from "react";
import { useProjects } from "@/hooks/useProject";
import { PRODUCTION_TYPE_LABELS, STATUS_LABELS } from "@/lib/constants";
import { formatDate } from "@/lib/utils";
import type { Project, ProductionType } from "@/types/project";

const STATUS_COLOR: Record<string, string> = {
  draft:           "bg-muted text-muted-foreground",
  generating:      "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
  assembly:        "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300",
  quality_review:  "bg-pink-100 text-pink-700 dark:bg-pink-900/30 dark:text-pink-300",
  human_review:    "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300",
  published:       "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300",
  failed:          "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300",
};

const TYPE_ICON: Record<ProductionType, typeof Video> = {
  short_video: Video,
  long_video:  Film,
  music_mv:    Music,
};

const TYPE_GRADIENT: Record<ProductionType, string> = {
  short_video: "from-violet-500 to-purple-700",
  long_video:  "from-blue-500 to-indigo-700",
  music_mv:    "from-pink-500 to-rose-700",
};

function ProjectCard({ project }: { project: Project }) {
  const Icon     = TYPE_ICON[project.production_type];
  const gradient = TYPE_GRADIENT[project.production_type];
  return (
    <Link
      href={`/projects/${project.id}`}
      className="group flex flex-col overflow-hidden rounded-2xl bg-card border border-border/50 card-shadow transition-all duration-200 hover:card-shadow-md hover:-translate-y-0.5"
    >
      {/* Top bar */}
      <div className={`flex h-1.5 w-full bg-gradient-to-r ${gradient}`} />
      <div className="flex flex-1 flex-col p-4 gap-3">
        <div className="flex items-start gap-3">
          <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br ${gradient}`}>
            <Icon className="h-4 w-4 text-white" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-foreground truncate group-hover:text-primary transition-colors">
              {project.title}
            </p>
            <p className="text-xs text-muted-foreground">
              {PRODUCTION_TYPE_LABELS[project.production_type]}
            </p>
          </div>
        </div>

        {project.topic && (
          <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
            {project.topic}
          </p>
        )}

        <div className="mt-auto flex items-center justify-between">
          <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium ${STATUS_COLOR[project.status] ?? "bg-muted text-muted-foreground"}`}>
            {STATUS_LABELS[project.status] ?? project.status}
          </span>
          <span className="text-[11px] text-muted-foreground">{formatDate(project.updated_at)}</span>
        </div>
      </div>
    </Link>
  );
}

export default function ProjectsPage() {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const { data, isLoading, error, mutate } = useProjects(page, 12);

  const filtered = data?.items.filter((p) =>
    search.trim() === "" ||
    p.title.toLowerCase().includes(search.toLowerCase()) ||
    (p.topic ?? "").toLowerCase().includes(search.toLowerCase())
  ) ?? [];

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Dự án</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {data ? `${data.total} dự án` : "Quản lý tất cả dự án sản xuất video"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => mutate()}
            className="flex h-9 w-9 items-center justify-center rounded-xl border border-border hover:bg-muted transition-colors text-muted-foreground"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
          <Link
            href="/create"
            className="flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            <Plus className="h-4 w-4" /> Tạo mới
          </Link>
        </div>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Tìm kiếm dự án..."
          className="w-full rounded-xl border border-border bg-card py-2.5 pl-10 pr-4 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 card-shadow"
        />
      </div>

      {/* Loading skeleton */}
      {isLoading && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-40 rounded-2xl bg-card border border-border/50 animate-pulse" />
          ))}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="flex flex-col items-center gap-3 rounded-2xl border border-border bg-card py-16 text-center">
          <AlertCircle className="h-8 w-8 text-destructive/60" />
          <p className="text-sm text-muted-foreground">Không kết nối được backend — hãy chạy server</p>
          <button onClick={() => mutate()} className="text-sm text-primary hover:underline">Thử lại</button>
        </div>
      )}

      {/* Empty state */}
      {!isLoading && !error && filtered.length === 0 && (
        <div className="flex flex-col items-center justify-center gap-4 rounded-2xl border border-dashed border-border py-20 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-muted">
            <Video className="h-6 w-6 text-muted-foreground/50" />
          </div>
          <div>
            <p className="font-medium">{search ? "Không tìm thấy kết quả" : "Chưa có dự án nào"}</p>
            <p className="mt-1 text-sm text-muted-foreground">
              {search ? "Thử từ khóa khác" : "Bắt đầu tạo video AI đầu tiên của bạn"}
            </p>
          </div>
          {!search && (
            <Link href="/create" className="flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90">
              <Plus className="h-4 w-4" /> Tạo dự án
            </Link>
          )}
        </div>
      )}

      {/* Grid */}
      {!isLoading && !error && filtered.length > 0 && (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {filtered.map((p) => <ProjectCard key={p.id} project={p} />)}
          </div>

          {/* Pagination */}
          {data && data.total > 12 && (
            <div className="flex justify-center gap-2 pt-2">
              <button
                disabled={page === 1}
                onClick={() => setPage(page - 1)}
                className="rounded-xl border border-border px-4 py-2 text-sm hover:bg-muted disabled:opacity-40 transition-colors"
              >
                ← Trước
              </button>
              <span className="flex items-center px-3 text-sm text-muted-foreground">
                Trang {page} / {Math.ceil(data.total / 12)}
              </span>
              <button
                disabled={page >= Math.ceil(data.total / 12)}
                onClick={() => setPage(page + 1)}
                className="rounded-xl border border-border px-4 py-2 text-sm hover:bg-muted disabled:opacity-40 transition-colors"
              >
                Tiếp →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
