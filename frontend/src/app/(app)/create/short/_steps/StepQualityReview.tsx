"use client";

import { useState, useEffect, useCallback } from "react";
import { CheckCircle2, XCircle, ArrowLeft, ArrowRight, Play, Loader2, Sparkles, RefreshCw, AlertCircle } from "lucide-react";
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
  const [decision, setDecision] = useState<boolean | null>(null);
  const [rejectNote, setRejectNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);

  // Load existing score on mount
  useEffect(() => {
    if (!projectId) return;
    fetch(`${BASE}/quality/${projectId}`)
      .then((r) => r.ok ? r.json() : null)
      .then((data) => {
        if (data && data.overall_score !== undefined) {
          setScore(data);
          setVideoUrl(data.video_url ?? null);
          if (data.human_approved !== null) setDecision(data.human_approved);
        }
      })
      .catch(() => {});
    // Load technical audit from pipeline state
    fetch(`${BASE}/pipeline/${projectId}/state`)
      .then((r) => r.ok ? r.json() : null)
      .then((st) => { if (st?.video_tech_audit) setTechAudit(st.video_tech_audit); })
      .catch(() => {});
  }, [projectId]);

  // SSE handler — listen for quality_scored event
  useSSE(scoring ? projectId : null, useCallback((event: { type: string; overall_score?: number; scores?: Record<string, number>; passed?: boolean; score_id?: string; message?: string }) => {
    if (event.type === "quality_scored") {
      setScoring(false);
      if (projectId) {
        fetch(`${BASE}/quality/${projectId}`)
          .then((r) => r.ok ? r.json() : null)
          .then((data) => {
            if (data) {
              setScore(data);
              setVideoUrl(data.video_url ?? null);
            }
          })
          .catch(() => {});
      }
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

  async function handleSubmitDecision() {
    if (!projectId || decision === null) return;
    setSubmitting(true);
    try {
      await fetch(`${BASE}/quality/${projectId}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          approved: decision,
          rejection_notes: !decision ? rejectNote : "",
        }),
      });
      if (decision) onNext();
    } finally {
      setSubmitting(false);
    }
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
          <h2 className="text-xl font-bold">Duyệt chất lượng video</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            GPT-5.4 Vision chấm điểm 7 tiêu chí — xem kết quả và duyệt
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
                <p className="font-medium text-sm">GPT-5.4 Vision đang phân tích...</p>
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
                  Nhấn "Chấm điểm" để GPT-5.4 Vision phân tích video
                </p>
              </div>
              <button
                onClick={handleTriggerScore}
                className="flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 transition-colors"
              >
                <Sparkles className="h-4 w-4" /> Chấm điểm ngay
              </button>
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
              Được chấm bởi: {score.model_used}
            </p>
          </div>

          {/* Score panel */}
          <div className="space-y-4">
            {/* Overall */}
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
                  <p className="text-xs text-green-600 dark:text-green-400 mt-0.5">✓ Đạt ngưỡng duyệt (≥ 75)</p>
                ) : (
                  <p className="text-xs text-amber-600 dark:text-amber-400 mt-0.5">⚠ Chưa đạt (cần ≥ 75)</p>
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

            {/* AI Feedback */}
            {score.gpt_feedback && (
              <div className="rounded-lg border border-border bg-muted/40 p-3">
                <p className="text-[11px] font-semibold text-muted-foreground mb-1">
                  Nhận xét GPT-5.4
                </p>
                <p className="text-xs leading-relaxed text-foreground/80">
                  {score.gpt_feedback}
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Human approval gate */}
      {score && (
        <div className="rounded-xl border border-border bg-card p-5 space-y-4">
          <p className="text-sm font-semibold">Quyết định của bạn</p>
          <div className="flex gap-3">
            <button
              onClick={() => setDecision(true)}
              className={cn(
                "flex flex-1 items-center justify-center gap-2 rounded-lg border-2 py-3 text-sm font-medium transition-all",
                decision === true
                  ? "border-green-500 bg-green-500/10 text-green-600 dark:text-green-400"
                  : "border-border hover:border-green-500/50"
              )}
            >
              <CheckCircle2 className="h-4 w-4" /> Duyệt — Tiếp tục SEO
            </button>
            <button
              onClick={() => setDecision(false)}
              className={cn(
                "flex flex-1 items-center justify-center gap-2 rounded-lg border-2 py-3 text-sm font-medium transition-all",
                decision === false
                  ? "border-destructive bg-destructive/10 text-destructive"
                  : "border-border hover:border-destructive/50"
              )}
            >
              <XCircle className="h-4 w-4" /> Từ chối — Tạo lại
            </button>
          </div>
          {decision === false && (
            <textarea
              value={rejectNote}
              onChange={(e) => setRejectNote(e.target.value)}
              placeholder="Ghi chú: phần nào cần cải thiện? (vd: clip cảnh 3 nhân vật không nhất quán)"
              rows={3}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 resize-none"
            />
          )}
          {decision !== null && (
            <button
              onClick={handleSubmitDecision}
              disabled={submitting}
              className={cn(
                "flex w-full items-center justify-center gap-2 rounded-lg py-2.5 text-sm font-semibold text-white transition-colors",
                decision ? "bg-green-600 hover:bg-green-700" : "bg-destructive hover:bg-destructive/90"
              )}
            >
              {submitting
                ? <Loader2 className="h-4 w-4 animate-spin" />
                : decision
                  ? <CheckCircle2 className="h-4 w-4" />
                  : <XCircle className="h-4 w-4" />}
              {decision ? "Xác nhận duyệt" : "Xác nhận từ chối"}
            </button>
          )}
        </div>
      )}

      <div className="flex justify-between pt-2">
        <button onClick={onBack} className="flex items-center gap-2 rounded-lg border border-border px-4 py-2.5 text-sm font-medium hover:bg-muted transition-colors">
          <ArrowLeft className="h-4 w-4" /> Quay lại
        </button>
        <button
          onClick={onNext}
          disabled={decision !== true}
          className="flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-40 transition-colors"
        >
          Tạo gói SEO <ArrowRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
