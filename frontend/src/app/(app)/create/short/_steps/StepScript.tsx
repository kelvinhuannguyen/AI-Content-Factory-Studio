"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Sparkles, ArrowLeft, ArrowRight, Check, AlertCircle, Loader2 } from "lucide-react";
import { useSSE } from "@/hooks/useSSE";
import { useWizardStore } from "@/stores/wizardStore";
import type { StepProps } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

type Phase =
  | "starting"       // starting pipeline
  | "writing"        // screenwriter / script_scorer running
  | "ready"          // script done — show it, no interrupt needed
  | "already_done"   // user navigated back from a later step
  | "error";

interface ScriptData {
  id: string;
  content_raw: string;
  content_html: string;
  word_count: number;
  estimated_duration_seconds: number;
}

export default function StepScript({ onNext, onBack }: StepProps) {
  const {
    project,
    characterDescription,
    characterName,
    setPipelineStarted,
    setScriptId,
  } = useWizardStore();

  const projectId = project?.id ?? null;
  const [phase, setPhase] = useState<Phase>("starting");
  const [script, setScript] = useState<ScriptData | null>(null);
  const [errorMsg, setErrorMsg] = useState("");
  const startedRef = useRef(false);

  async function loadScript() {
    if (!projectId) return;
    try {
      const res = await fetch(`${BASE}/scripts/${projectId}`);
      if (res.ok) {
        const data = await res.json();
        setScript(data);
        setScriptId(data.id, false);
      }
    } catch { /* silent */ }
  }

  async function syncState() {
    if (!projectId) return;
    try {
      const res = await fetch(`${BASE}/pipeline/${projectId}/state`);
      if (!res.ok) return;
      const state = await res.json();

      if (state.status === "not_started") {
        setPhase("starting");
        await startPipeline();
      } else if (
        state.current_stage === "character_designer" ||
        state.current_stage === "character_scorer" ||
        state.current_stage === "character_review" ||
        state.current_stage === "scene_planner" ||
        state.current_stage === "cinematic_decomposer" ||
        state.current_stage === "shot_review" ||
        state.current_stage === "continuity_director" ||
        state.current_stage === "video_editor" ||
        state.current_stage === "video_validator" ||
        state.current_stage === "seo_agent" ||
        state.current_stage === "seo_review" ||
        state.paused_at === "character_review" ||
        state.paused_at === "shot_review" ||
        state.paused_at === "seo_review" ||
        state.status === "completed"
      ) {
        await loadScript();
        setPhase("already_done");
      } else if (
        state.current_stage === "screenwriter" ||
        state.current_stage === "script_scorer" ||
        state.status === "running"
      ) {
        setPhase("writing");
      }
    } catch {
      setPhase("error");
      setErrorMsg("Không kết nối được backend");
    }
  }

  async function startPipeline() {
    if (!projectId) return;
    try {
      const res = await fetch(`${BASE}/pipeline/${projectId}/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          character_description: characterDescription ?? "",
          character_name: characterName ?? "",
        }),
      });
      if (res.status === 409) { await syncState(); return; }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setPipelineStarted(true);
      setPhase("writing");
    } catch (e: any) {
      setPhase("error");
      setErrorMsg(e.message ?? "Không thể khởi động pipeline");
    }
  }

  const handleSSE = useCallback((event: any) => {
    const { type, agent } = event;

    if (type === "agent_start" && (agent === "screenwriter" || agent === "script_scorer")) {
      setPhase(p => p === "ready" || p === "already_done" ? p : "writing");
    }

    if (type === "agent_done" && agent === "script_scorer" && !event.will_retry) {
      loadScript();
      setPhase("ready");
    }

    if (type === "agent_start" && agent === "character_designer") {
      setPhase(p => p === "already_done" ? p : "ready");
    }

    if (type === "agent_error" && agent === "screenwriter") {
      setPhase("error");
      setErrorMsg(event.error ?? "Lỗi viết kịch bản");
    }
  }, [projectId]);

  useSSE(projectId, handleSSE);

  useEffect(() => {
    if (!projectId || startedRef.current) return;
    startedRef.current = true;
    syncState();
  }, [projectId]);

  const isLoading = phase === "starting" || phase === "writing";

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold">Kịch bản AI</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {phase === "already_done"
              ? "Kịch bản đã hoàn thành — pipeline đang tiếp tục"
              : "Gemini viết kịch bản chuẩn Hollywood · Chấm điểm AI tự động"}
          </p>
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center gap-3 rounded-xl border border-primary/20 bg-primary/5 p-4">
          <Loader2 className="h-5 w-5 animate-spin text-primary shrink-0" />
          <div>
            <p className="text-sm font-medium text-primary">
              {phase === "starting" ? "Đang khởi động pipeline..." : "AI đang viết kịch bản Hollywood..."}
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">
              Pipeline LangGraph đang chạy · Kịch bản sẽ hiện khi hoàn thành
            </p>
          </div>
        </div>
      )}

      {phase === "error" && (
        <div className="flex items-center gap-3 rounded-xl border border-destructive/20 bg-destructive/5 p-4">
          <AlertCircle className="h-5 w-5 text-destructive shrink-0" />
          <div className="flex-1">
            <p className="text-sm text-destructive">{errorMsg}</p>
          </div>
          <button
            onClick={() => { startedRef.current = false; syncState(); }}
            className="text-xs text-primary hover:underline"
          >
            Thử lại
          </button>
        </div>
      )}

      {phase === "already_done" && (
        <div className="rounded-xl border border-green-500/30 bg-green-500/5 p-4 flex items-center gap-3">
          <Check className="h-5 w-5 text-green-500 shrink-0" />
          <div className="flex-1">
            <p className="text-sm font-semibold text-green-700 dark:text-green-400">Kịch bản đã hoàn thành ✓</p>
            {script && (
              <p className="text-xs text-muted-foreground mt-0.5">{script.word_count} từ · Pipeline đang tiếp tục tự động</p>
            )}
          </div>
        </div>
      )}

      {(phase === "ready" || phase === "already_done") && script && (
        <>
          <div className="flex flex-wrap gap-2">
            <span className="rounded-full bg-muted px-3 py-1 text-xs font-medium text-muted-foreground">
              📝 {script.word_count} từ
            </span>
            <span className="rounded-full bg-muted px-3 py-1 text-xs font-medium text-muted-foreground">
              ⏱ ~{Math.ceil(script.estimated_duration_seconds / 60)} phút
            </span>
            <span className="rounded-full bg-green-500/10 border border-green-500/20 px-3 py-1 text-xs font-medium text-green-700 dark:text-green-400">
              <Sparkles className="h-3 w-3 inline mr-1" />Đã đạt điểm AI ✓
            </span>
          </div>

          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Nội dung kịch bản</p>
            <div
              className="prose prose-sm dark:prose-invert max-w-none rounded-xl border border-border bg-card px-5 py-4 text-sm leading-relaxed"
              dangerouslySetInnerHTML={{ __html: script.content_html || `<p>${script.content_raw}</p>` }}
            />
          </div>
        </>
      )}

      <div className="flex justify-between pt-2">
        <button
          onClick={onBack}
          className="flex items-center gap-2 rounded-xl border border-border px-4 py-2.5 text-sm font-medium hover:bg-muted transition-colors"
        >
          <ArrowLeft className="h-4 w-4" /> Quay lại
        </button>
        {(phase === "ready" || phase === "already_done") && (
          <button
            onClick={onNext}
            className="flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            Tiếp theo <ArrowRight className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
}
