"use client";

import { useState, useEffect, useCallback } from "react";
import { CheckCircle2, ArrowLeft, ArrowRight, Play, Loader2, Sparkles, RefreshCw, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { useSSE } from "@/hooks/useSSE";
import { useWizardStore } from "@/stores/wizardStore";
import type { StepProps } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

interface Dimension {
  label: string;
  field: string;
  max: number;
}

const DIMENSIONS: Dimension[] = [
  { label: "Sức hút hook (3s đầu)", field: "hook_strength",         max: 20 },
  { label: "Mạch câu chuyện",       field: "story_coherence",       max: 20 },
  { label: "Chất lượng hình ảnh",   field: "visual_quality",        max: 20 },
  { label: "Âm thanh & đồng bộ",    field: "audio_sync",            max: 15 },
  { label: "Nhất quán nhân vật",     field: "character_consistency", max: 10 },
  { label: "Nhịp độ & cắt cảnh",    field: "pacing",                max: 10 },
  { label: "Tiềm năng tương tác",   field: "engagement_potential",  max:  5 },
];

interface ScoreData {
  id: string;
  overall_score: number;
  passed: boolean;
  dimensions: Record<string, { score: number; max: number }>;
  gpt_feedback: string;
  human_approved: boolean | null;
  model_used: string;
  video_url: string | null;
}

export default function StepQualityReview({ onNext, onBack }: StepProps) {
  const { project } = useWizardStore();
  const projectId = project?.id ?? null;

  interface TechAudit {
    codec?: string; codec_ok?: boolean;
    height?: number; resolution_ok?: boolean;
    fps?: number; fps_ok?: boolean;
    bitrate_kbps?: number; bitrate_ok?: boolean;
    audio_codec?: string; audio_ok?: boolean;
    duration_s?: number; duration_ok?: boolean;
    error?: string;
  }

  const [score, setScore] = useState<ScoreData | null>(null);
  const [techAudit, setTechAudit] = useState<TechAudit | null>(null);
  const [scoring, setScoring] = useState(false);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [seoStarted, setSeoStarted] = useState(false);

  useEffect(() => {
    if (!projectId) return;
    fetch(`${BASE}/quality/${projectId}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data && data.overall_score !== undefined) {
          setScore(data);
          setVideoUrl(data.video_url ?? null);
        }
      })
      .catch(() => {});
    fetch(`${BASE}/pipeline/${projectId}/state`)
      .then(r => r.ok ? r.json() : null)
      .then(st => {
        if (st?.video_tech_audit) setTechAudit(st.video_tech_audit);
        // If already past video_validator, show "Tiếp theo" as active
        if (
          st?.current_stage === "seo_agent" ||
          st?.current_stage === "seo_review" ||
          st?.paused_at === "seo_review" ||
          st?.status === "completed"
        ) {
          setSeoStarted(true);
        }
      })
      .catch(() => {});
  }, [projectId]);

  // SSE: listen for video_validator done (auto-routes to seo_agent)
  useSSE(projectId, useCallback((event: { type: string; agent?: string; overall_score?: number; scores?: Record<string, number>; passed?: boolean; score_id?: string; message?: string }) => {
    if (event.type === "agent_done" && event.agent === "video_validator") {
      setScoring(false);
      if (projectId) {
        fetch(`${BASE}/quality/${projectId}`)
          .then(r => r.ok ? r.json() : null)
          .then(data => {
            if (data) { setScore(data); setVideoUrl(data.video_url ?? null); }
          })
          .catch(() => {});
      }
    }
    if (event.type === "agent_start" && event.agent === "seo_agent") {
      setSeoStarted(true);
    }
  }, [projectId]));

  async function handleTriggerScore() {
    if (!projectId) return;
    setScoring(true);
    setScore(null);
    await fetch(`${BASE}/quality/score`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_id: projectId }),
    }).catch(() => setScoring(false));
  }

  const scoreColor = (overall: number) =>
    overall >= 80 ? "text-green-600 dark:text-green-400" :
    overall >= 75 ? "text-primary" :
    overall >= 60 ? "text-amber-600 dark:text-amber-400" :
    "text-destructive";

  const barColor = (pct: number) =>
    pct >= 80 ? "bg-green-500" :
    pct >= 60 ? "bg-primary" :
    pct >= 40 ? "bg-amber-500" :
    "bg-destructive";

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-xl font-bold">Kiểm tra chất lượng video</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            AI chấm điểm 7 tiêu chí + kiểm tra kỹ thuật — tự động tiếp tục sang SEO
          </p>
        </div>
        <button
          onClick={handleTriggerScore}
          disabled={scoring}
          className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-xs font-medium hover:bg-muted transition-colors disabled:opacity-50"
        >
          {scoring
            ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
            : <RefreshCw className="h-3.5 w-3.5" />}
          {score ? "Chấm lại" : "Chấm điểm"}
        </button>
      </div>

      {/* Auto-advance notice when seo_agent started */}
      {seoStarted && (
        <div className="rounded-xl border border-green-500/30 bg-green-500/5 p-4 flex items-center gap-3">
          <CheckCircle2 className="h-5 w-5 text-green-500 shrink-0" />
          <div>
            <p className="text-sm font-semibold text-green-700 dark:text-green-400">Video đã vượt qua kiểm tra ✓</p>
            <p className="text-xs text-muted-foreground mt-0.5">SEO Agent đang tạo gói metadata — tiến tới Trạm 3</p>
          </div>
        </div>
      )}

      {/* Technical audit panel */}
      {techAudit && !techAudit.error && (
        <div className="rounded-lg border border-border p-3 space-y-2">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Kiểm tra kỹ thuật</p>
          <div className="grid grid-cols-3 gap-x-4 gap-y-1.5">
            {([
              { label: "Codec",        ok: techAudit.codec_ok,       value: techAudit.codec },
              { label: "Độ phân giải", ok: techAudit.resolution_ok,  value: techAudit.height ? `${techAudit.height}p` : "—" },
              { label: "FPS",          ok: techAudit.fps_ok,         value: techAudit.fps ? `${techAudit.fps}fps` : "—" },
              { label: "Bitrate",      ok: techAudit.bitrate_ok,     value: techAudit.bitrate_kbps ? `${techAudit.bitrate_kbps}kbps` : "—" },
              { label: "Audio",        ok: techAudit.audio_ok,       value: techAudit.audio_codec },
              { label: "Thời lượng",   ok: techAudit.duration_ok,    value: techAudit.duration_s ? `${techAudit.duration_s}s` : "—" },
            ] as { label: string; ok?: boolean; value?: string | number }[]).map(({ label, ok, value }) => (
              <div key={label} className="flex items-center gap-1.5 text-xs">
                {ok
                  ? <CheckCircle2 className="h-3 w-3 text-green-500 shrink-0" />
                  : <AlertCircle className="h-3 w-3 text-amber-500 shrink-0" />}
                <span className="text-muted-foreground">{label}:</span>
                <span className="font-medium">{String(value ?? "—")}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Empty / loading state */}
      {!score && (
        <div className="flex flex-col items-center gap-4 rounded-xl border border-dashed border-border py-14 text-center">
          {scoring ? (
            <>
              <Loader2 className="h-10 w-10 animate-spin text-primary/50" />
              <div>
                <p className="font-medium text-sm">AI đang phân tích video...</p>
                <p className="text-xs text-muted-foreground mt-1">
                  Đang trích xuất keyframes và chấm 7 tiêu chí
                </p>
              </div>
            </>
          ) : (
            <>
              <Sparkles className="h-10 w-10 text-primary/40" />
              <div>
                <p className="font-medium text-sm">Chưa có điểm chất lượng</p>
                <p className="text-xs text-muted-foreground mt-1">
                  Video đang được tạo — điểm sẽ hiện tự động sau khi xong
                </p>
              </div>
            </>
          )}
        </div>
      )}

      {score && (
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
          {/* Video preview */}
          <div className="space-y-2">
            <div className="aspect-video w-full overflow-hidden rounded-xl border border-border bg-muted flex items-center justify-center">
              {videoUrl ? (
                <video src={videoUrl} controls className="h-full w-full rounded-xl object-contain" />
              ) : (
                <div className="text-center">
                  <Play className="h-10 w-10 text-muted-foreground/30 mx-auto" />
                  <p className="mt-2 text-xs text-muted-foreground">final.mp4</p>
                </div>
              )}
            </div>
            <p className="text-[10px] text-center text-muted-foreground">
              Chấm bởi: {score.model_used}
            </p>
          </div>

          {/* Score panel */}
          <div className="space-y-4">
            <div className={cn(
              "flex items-center gap-4 rounded-xl border p-4",
              score.passed ? "border-green-500/40 bg-green-500/5" : "border-amber-500/40 bg-amber-500/5"
            )}>
              <div className={cn("text-5xl font-black tabular-nums", scoreColor(score.overall_score))}>
                {score.overall_score}
              </div>
              <div>
                <p className="text-sm font-bold">/ 100 điểm</p>
                {score.passed ? (
                  <p className="text-xs text-green-600 dark:text-green-400 mt-0.5">✓ Đạt ngưỡng (≥ 75) — Tự động tiếp tục SEO</p>
                ) : (
                  <p className="text-xs text-amber-600 dark:text-amber-400 mt-0.5">⚠ Chưa đạt (cần ≥ 75) — Đang retry...</p>
                )}
              </div>
            </div>

            {/* Dimension bars */}
            <div className="space-y-2.5">
              {DIMENSIONS.map(({ label, field, max }) => {
                const v = score.dimensions[field]?.score ?? 0;
                const pct = Math.round((v / max) * 100);
                return (
                  <div key={field} className="space-y-1">
                    <div className="flex justify-between text-xs">
                      <span className="text-muted-foreground">{label}</span>
                      <span className="font-semibold tabular-nums">{v}<span className="font-normal text-muted-foreground">/{max}</span></span>
                    </div>
                    <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                      <div
                        className={cn("h-full rounded-full transition-all duration-700", barColor(pct))}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>

            {score.gpt_feedback && (
              <div className="rounded-lg border border-border bg-muted/40 p-3">
                <p className="text-[11px] font-semibold text-muted-foreground mb-1">Nhận xét AI</p>
                <p className="text-xs leading-relaxed text-foreground/80">{score.gpt_feedback}</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Informational notice — no human approval needed */}
      {score && !seoStarted && (
        <div className="rounded-xl border border-border bg-muted/30 p-4 text-center">
          <p className="text-xs text-muted-foreground">
            Không cần duyệt thủ công — pipeline tự động tiếp tục sang Trạm 3 (SEO + Xuất bản).
          </p>
        </div>
      )}

      <div className="flex justify-between pt-2">
        <button onClick={onBack} className="flex items-center gap-2 rounded-lg border border-border px-4 py-2.5 text-sm font-medium hover:bg-muted transition-colors">
          <ArrowLeft className="h-4 w-4" /> Quay lại
        </button>
        <button
          onClick={onNext}
          disabled={!score && !seoStarted}
          className="flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-40 transition-colors"
        >
          Tới Trạm 3 — SEO <ArrowRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
