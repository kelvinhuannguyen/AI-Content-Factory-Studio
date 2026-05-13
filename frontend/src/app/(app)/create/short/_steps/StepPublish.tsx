"use client";

import { useState, useEffect, useRef } from "react";
import {
  Youtube, Download, Globe, Lock, EyeOff, CheckCircle2,
  ArrowLeft, Loader2, ExternalLink, Play, Pause, Volume2
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useWizardStore } from "@/stores/wizardStore";
import type { StepProps } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

type Privacy = "public" | "unlisted" | "private";

const PRIVACY_OPTIONS: { value: Privacy; icon: typeof Globe; label: string; desc: string }[] = [
  { value: "public",   icon: Globe,   label: "Công khai",     desc: "Mọi người đều có thể xem" },
  { value: "unlisted", icon: EyeOff,  label: "Không liệt kê", desc: "Chỉ người có link mới xem được" },
  { value: "private",  icon: Lock,    label: "Riêng tư",      desc: "Chỉ mình bạn xem được" },
];

export default function StepPublish({ onBack }: StepProps) {
  const { project } = useWizardStore();
  const projectId = project?.id;

  const [privacy, setPrivacy]               = useState<Privacy>("unlisted");
  const [uploading, setUploading]           = useState(false);
  const [uploadError, setUploadError]       = useState<string | null>(null);
  const [youtubeUrl, setYoutubeUrl]         = useState<string | null>(null);
  const [downloadUrl, setDownloadUrl]       = useState<string | null>(null);
  const [downloadLoading, setDownloadLoading] = useState(false);
  const [isPlaying, setIsPlaying]           = useState(false);
  const [videoLoading, setVideoLoading]     = useState(true);
  const [publishStatus, setPublishStatus]   = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  // Load presigned download URL + check existing publish status on mount
  useEffect(() => {
    if (!projectId) return;

    // Fetch video preview URL
    setVideoLoading(true);
    fetch(`${BASE}/publish/${projectId}/download`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data?.download_url) setDownloadUrl(data.download_url);
      })
      .catch(() => {})
      .finally(() => setVideoLoading(false));

    // Check if already published
    fetch(`${BASE}/publish/${projectId}/status`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data?.youtube_url) setYoutubeUrl(data.youtube_url);
        if (data?.project_status) setPublishStatus(data.project_status);
      })
      .catch(() => {});
  }, [projectId]);

  function togglePlay() {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) { v.play(); setIsPlaying(true); }
    else          { v.pause(); setIsPlaying(false); }
  }

  async function handleDownload() {
    if (!projectId) return;
    setDownloadLoading(true);
    try {
      const res = await fetch(`${BASE}/publish/${projectId}/download`);
      if (res.ok) {
        const data = await res.json();
        setDownloadUrl(data.download_url);
        const a = document.createElement("a");
        a.href = data.download_url;
        a.download = `video_${projectId.slice(0, 8)}.mp4`;
        a.click();
      }
    } finally {
      setDownloadLoading(false);
    }
  }

  async function handlePublish() {
    if (!projectId) return;
    setUploading(true);
    setUploadError(null);
    try {
      const res = await fetch(`${BASE}/publish/youtube`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId, privacy }),
      });
      const data = await res.json();
      if (!res.ok) {
        setUploadError(data.detail || "Upload thất bại");
      } else {
        setYoutubeUrl(data.youtube_url);
        setPublishStatus("published");
      }
    } catch {
      setUploadError("Lỗi kết nối — kiểm tra backend");
    } finally {
      setUploading(false);
    }
  }

  const published = !!youtubeUrl || publishStatus === "published";

  // ── Success screen ──────────────────────────────────────────────────────
  if (published && youtubeUrl) {
    return (
      <div className="mx-auto max-w-xl space-y-6 text-center">
        <div className="flex flex-col items-center gap-4 pt-6">
          <div className="flex h-20 w-20 items-center justify-center rounded-full bg-green-500/10">
            <CheckCircle2 className="h-10 w-10 text-green-500" />
          </div>
          <h2 className="text-2xl font-bold">Video đã đăng thành công!</h2>
          <p className="text-sm text-muted-foreground">
            Quyền riêng tư: <span className="font-semibold text-foreground">
              {privacy === "public" ? "Công khai" : privacy === "unlisted" ? "Không liệt kê" : "Riêng tư"}
            </span>
          </p>
          <code className="rounded-lg bg-muted px-3 py-1.5 text-xs break-all max-w-full">{youtubeUrl}</code>
        </div>
        <div className="flex flex-wrap gap-3 justify-center">
          <a href={youtubeUrl} target="_blank" rel="noopener noreferrer"
             className="flex items-center gap-2 rounded-lg bg-red-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-red-700 transition-colors">
            <Youtube className="h-4 w-4" /> Xem trên YouTube
          </a>
          <a href="https://studio.youtube.com" target="_blank" rel="noopener noreferrer"
             className="flex items-center gap-2 rounded-lg border border-border px-5 py-2.5 text-sm font-medium hover:bg-muted transition-colors">
            <ExternalLink className="h-4 w-4" /> YouTube Studio
          </a>
          <button onClick={handleDownload} disabled={downloadLoading}
             className="flex items-center gap-2 rounded-lg border border-border px-5 py-2.5 text-sm font-medium hover:bg-muted transition-colors disabled:opacity-50">
            {downloadLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            Tải MP4
          </button>
        </div>
        <button onClick={onBack} className="flex items-center gap-2 rounded-lg border border-border px-4 py-2.5 text-sm font-medium hover:bg-muted transition-colors mx-auto">
          <ArrowLeft className="h-4 w-4" /> Quay lại
        </button>
      </div>
    );
  }

  // ── Main screen ─────────────────────────────────────────────────────────
  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div>
        <h2 className="text-xl font-bold">Xem trước & Đăng bài</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Kiểm tra video lần cuối trước khi đăng lên YouTube
        </p>
      </div>

      {/* ── Video preview section ── */}
      <div className="space-y-3">
        <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
          Xem trước video
        </label>

        <div className="relative overflow-hidden rounded-xl border border-border bg-black aspect-video">
          {downloadUrl ? (
            <>
              <video
                ref={videoRef}
                src={downloadUrl}
                className="h-full w-full object-contain"
                onPlay={() => setIsPlaying(true)}
                onPause={() => setIsPlaying(false)}
                onEnded={() => setIsPlaying(false)}
                onLoadedData={() => setVideoLoading(false)}
                preload="metadata"
                playsInline
              />
              {/* Play overlay */}
              {!isPlaying && (
                <button
                  onClick={togglePlay}
                  className="absolute inset-0 flex items-center justify-center bg-black/30 hover:bg-black/40 transition-colors group"
                >
                  <div className="flex h-16 w-16 items-center justify-center rounded-full bg-white/90 shadow-lg group-hover:scale-105 transition-transform">
                    <Play className="h-7 w-7 text-black ml-1" />
                  </div>
                </button>
              )}
              {/* Pause button when playing */}
              {isPlaying && (
                <button
                  onClick={togglePlay}
                  className="absolute bottom-3 right-3 flex h-8 w-8 items-center justify-center rounded-full bg-black/60 text-white hover:bg-black/80 transition-colors"
                >
                  <Pause className="h-4 w-4" />
                </button>
              )}
            </>
          ) : videoLoading ? (
            <div className="flex h-full items-center justify-center">
              <Loader2 className="h-8 w-8 animate-spin text-white/40" />
            </div>
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-white/40">
              <Volume2 className="h-10 w-10" />
              <p className="text-sm">Video chưa sẵn sàng</p>
              <p className="text-xs">Cần hoàn thành bước tạo video trước</p>
            </div>
          )}
        </div>

        {/* Download button under preview */}
        <button
          onClick={handleDownload}
          disabled={!downloadUrl || downloadLoading}
          className="flex w-full items-center justify-center gap-2 rounded-lg border border-border py-2.5 text-sm font-medium hover:bg-muted transition-colors disabled:opacity-40"
        >
          {downloadLoading
            ? <Loader2 className="h-4 w-4 animate-spin" />
            : <Download className="h-4 w-4" />}
          Tải MP4 về máy
        </button>

        {!downloadUrl && !videoLoading && (
          <p className="text-xs text-center text-muted-foreground">
            Presigned URL tự hết hạn sau 1 giờ — nhấn "Tải MP4" để làm mới link.
          </p>
        )}
      </div>

      {/* ── Divider ── */}
      <div className="flex items-center gap-3">
        <div className="flex-1 border-t border-border" />
        <span className="text-xs text-muted-foreground">Hoặc đăng lên YouTube</span>
        <div className="flex-1 border-t border-border" />
      </div>

      {/* ── Privacy selector ── */}
      <div className="space-y-2">
        <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
          Quyền riêng tư
        </label>
        {PRIVACY_OPTIONS.map(({ value, icon: Icon, label, desc }) => (
          <button
            key={value}
            onClick={() => setPrivacy(value)}
            className={cn(
              "flex w-full items-center gap-4 rounded-lg border p-3.5 text-left transition-all",
              privacy === value ? "border-primary bg-primary/5" : "border-border hover:border-primary/30"
            )}
          >
            <Icon className={cn("h-4 w-4 shrink-0", privacy === value ? "text-primary" : "text-muted-foreground")} />
            <div className="flex-1">
              <p className="text-sm font-medium leading-tight">{label}</p>
              <p className="text-xs text-muted-foreground">{desc}</p>
            </div>
            {privacy === value && (
              <div className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-primary">
                <CheckCircle2 className="h-3 w-3 text-white" />
              </div>
            )}
          </button>
        ))}
      </div>

      {/* YouTube OAuth note */}
      <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-xs text-amber-700 dark:text-amber-400 leading-relaxed">
        YouTube upload yêu cầu OAuth2 credentials.
        Cấu hình <code className="font-mono">YOUTUBE_CLIENT_ID</code> +{" "}
        <code className="font-mono">YOUTUBE_CLIENT_SECRET</code> trong <strong>.env</strong>.
      </div>

      {/* Error */}
      {uploadError && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {uploadError}
        </div>
      )}

      {/* Publish button */}
      <button
        onClick={handlePublish}
        disabled={uploading}
        className="flex w-full items-center justify-center gap-2 rounded-lg bg-red-600 py-3 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
      >
        {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Youtube className="h-4 w-4" />}
        {uploading ? "Đang đăng lên YouTube..." : "Đăng lên YouTube"}
      </button>

      <div className="flex justify-between pt-1">
        <button onClick={onBack} className="flex items-center gap-2 rounded-lg border border-border px-4 py-2.5 text-sm font-medium hover:bg-muted transition-colors">
          <ArrowLeft className="h-4 w-4" /> Quay lại
        </button>
      </div>
    </div>
  );
}
