"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Sparkles, ArrowLeft, ArrowRight, Check, AlertCircle, RefreshCw, Loader2, RotateCcw } from "lucide-react";
import { useSSE } from "@/hooks/useSSE";
import { useWizardStore } from "@/stores/wizardStore";
import type { StepProps } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

type Phase =
  | "starting"       // đang start pipeline lần đầu
  | "writing"        // LangGraph screenwriter đang viết
  | "ready"          // script sẵn sàng, chờ duyệt
  | "approving"      // đang gửi approve
  | "rejecting"      // đang gửi reject
  | "rewriting"      // đã reject, screenwriter đang viết lại
  | "already_done"   // kịch bản đã duyệt (user quay lại từ bước sau)
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
    setScriptApproved,
  } = useWizardStore();

  const projectId = project?.id ?? null;
  const [phase, setPhase] = useState<Phase>("starting");
  const [script, setScript] = useState<ScriptData | null>(null);
  const [rejectionNotes, setRejectionNotes] = useState("");
  const [showNotesForm, setShowNotesForm] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const startedRef = useRef(false); // prevent double-start in StrictMode

  // Load script from API
  async function loadScript() {
    if (!projectId) return;
    try {
      const res = await fetch(`${BASE}/scripts/${projectId}`);
      if (res.ok) {
        const data = await res.json();
        setScript(data);
        setScriptId(data.id, false);
      }
    } catch {
      // silent — script may not exist yet
    }
  }

  // Check pipeline state and load existing data
  async function syncState() {
    if (!projectId) return;
    try {
      const res = await fetch(`${BASE}/pipeline/${projectId}/state`);
      if (!res.ok) return;
      const state = await res.json();

      if (state.status === "not_started") {
        // Need to start pipeline
        setPhase("starting");
        await startPipeline();
      } else if (state.paused_at === "script_review") {
        // Paused waiting for script approval
        await loadScript();
        setPhase("ready");
      } else if (
        state.current_stage === "character_designer" ||
        state.current_stage === "character_review" ||
        state.current_stage === "scene_planner" ||
        state.current_stage === "scene_review" ||
        state.current_stage === "video_generator" ||
        state.status === "completed"
      ) {
        // Already past script review — user came back
        await loadScript();
        setPhase("already_done");
      } else if (state.status === "running") {
        // Screenwriter still writing
        setPhase("writing");
      }
    } catch (e) {
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

      if (res.status === 409) {
        // Already running — sync state
        await syncState();
        return;
      }
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      setPipelineStarted(true);
      setPhase("writing");
    } catch (e: any) {
      setPhase("error");
      setErrorMsg(e.message ?? "Không thể khởi động pipeline");
    }
  }

  // SSE handler — listen for LangGraph agent events
  const handleSSE = useCallback((event: any) => {
    const { type, agent, step } = event;

    if (type === "agent_start" && agent === "screenwriter") {
      setPhase((p) => p === "rewriting" || p === "writing" ? "writing" : p);
    }

    if (type === "agent_interrupt" && step === "script_review") {
      loadScript();
      setPhase("ready");
      setShowNotesForm(false);
      setRejectionNotes("");
    }

    if (type === "agent_error" && agent === "screenwriter") {
      setPhase("error");
      setErrorMsg(event.error ?? "Lỗi viết kịch bản");
    }
  }, [projectId]);

  useSSE(projectId, handleSSE);

  // On mount: sync with pipeline state
  useEffect(() => {
    if (!projectId || startedRef.current) return;
    startedRef.current = true;
    syncState();
  }, [projectId]);

  async function handleApprove() {
    if (!projectId) return;
    setPhase("approving");
    try {
      await fetch(`${BASE}/pipeline/${projectId}/resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ step: "script", approved: true }),
      });
      setScriptApproved(true);
      onNext();
    } catch {
      setPhase("ready");
    }
  }

  async function handleReject() {
    if (!projectId) return;
    setPhase("rejecting");
    try {
      await fetch(`${BASE}/pipeline/${projectId}/resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ step: "script", approved: false, notes: rejectionNotes }),
      });
      setScript(null);
      setShowNotesForm(false);
      setRejectionNotes("");
      setPhase("rewriting");
    } catch {
      setPhase("ready");
    }
  }

  // ── Render helpers ─────────────────────────────────────────────────────────

  const isLoading = phase === "starting" || phase === "writing" || phase === "rewriting";
  const isSubmitting = phase === "approving" || phase === "rejecting";

  const loadingMessage: Record<string, string> = {
    starting: "Đang khởi động pipeline...",
    writing:  "AI đang viết kịch bản Hollywood...",
    rewriting: "AI đang viết lại kịch bản...",
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold">Kịch bản AI</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {phase === "already_done"
              ? "Kịch bản đã được duyệt — tiếp tục pipeline"
              : "Gemini viết kịch bản chuẩn Hollywood · Chờ duyệt qua email hoặc bấm bên dưới"}
          </p>
        </div>
      </div>

      {/* Loading state */}
      {isLoading && (
        <div className="flex items-center gap-3 rounded-xl border border-primary/20 bg-primary/5 p-4">
          <Loader2 className="h-5 w-5 animate-spin text-primary shrink-0" />
          <div>
            <p className="text-sm font-medium text-primary">{loadingMessage[phase]}</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              Pipeline LangGraph đang chạy · Bạn sẽ nhận email khi kịch bản xong
            </p>
          </div>
        </div>
      )}

      {/* Error state */}
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

      {/* Already approved — back-navigation state */}
      {phase === "already_done" && script && (
        <div className="rounded-xl border border-green-500/30 bg-green-500/5 p-4 flex items-center gap-3">
          <Check className="h-5 w-5 text-green-500 shrink-0" />
          <div className="flex-1">
            <p className="text-sm font-semibold text-green-700 dark:text-green-400">Kịch bản đã duyệt</p>
            <p className="text-xs text-muted-foreground mt-0.5">{script.word_count} từ · Pipeline đang tiếp tục</p>
          </div>
        </div>
      )}

      {/* Script ready for review */}
      {(phase === "ready" || phase === "approving" || phase === "rejecting" || phase === "already_done") && script && (
        <>
          {/* Metadata chips */}
          <div className="flex flex-wrap gap-2">
            <span className="rounded-full bg-muted px-3 py-1 text-xs font-medium text-muted-foreground">
              📝 {script.word_count} từ
            </span>
            <span className="rounded-full bg-muted px-3 py-1 text-xs font-medium text-muted-foreground">
              ⏱ ~{Math.ceil(script.estimated_duration_seconds / 60)} phút
            </span>
          </div>

          {/* Script content */}
          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Nội dung kịch bản</p>
            <div
              className="prose prose-sm dark:prose-invert max-w-none rounded-xl border border-border bg-card px-5 py-4 text-sm leading-relaxed"
              dangerouslySetInnerHTML={{ __html: script.content_html || `<p>${script.content_raw}</p>` }}
            />
          </div>

          {/* Rejection notes form */}
          {showNotesForm && (
            <div className="space-y-2">
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                Ghi chú cho AI (tuỳ chọn)
              </label>
              <textarea
                value={rejectionNotes}
                onChange={(e) => setRejectionNotes(e.target.value)}
                rows={3}
                placeholder="Ví dụ: Cần thêm kịch tính ở cảnh 2, hook cần mạnh hơn..."
                className="w-full rounded-xl border border-border bg-card px-4 py-3 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 resize-none"
              />
              <div className="flex gap-2">
                <button
                  onClick={handleReject}
                  disabled={isSubmitting}
                  className="flex items-center gap-2 rounded-xl bg-destructive px-4 py-2 text-sm font-semibold text-destructive-foreground hover:bg-destructive/90 disabled:opacity-50"
                >
                  {phase === "rejecting"
                    ? <Loader2 className="h-4 w-4 animate-spin" />
                    : <RotateCcw className="h-4 w-4" />
                  }
                  Tạo lại kịch bản
                </button>
                <button
                  onClick={() => setShowNotesForm(false)}
                  className="rounded-xl border border-border px-4 py-2 text-sm font-medium hover:bg-muted"
                >
                  Huỷ
                </button>
              </div>
            </div>
          )}

          {/* Action buttons — only show when awaiting decision */}
          {phase === "ready" && !showNotesForm && (
            <div className="flex gap-3">
              <button
                onClick={() => setShowNotesForm(true)}
                className="flex items-center gap-2 rounded-xl border border-border px-4 py-2.5 text-sm font-medium hover:bg-muted transition-colors"
              >
                <RefreshCw className="h-4 w-4" /> Tạo lại
              </button>
              <button
                onClick={handleApprove}
                disabled={isSubmitting}
                className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
              >
                {phase === "approving"
                  ? <Loader2 className="h-4 w-4 animate-spin" />
                  : <Check className="h-4 w-4" />
                }
                Duyệt kịch bản
              </button>
            </div>
          )}
        </>
      )}

      <div className="flex justify-between pt-2">
        <button
          onClick={onBack}
          className="flex items-center gap-2 rounded-xl border border-border px-4 py-2.5 text-sm font-medium hover:bg-muted transition-colors"
        >
          <ArrowLeft className="h-4 w-4" /> Quay lại
        </button>
        {/* Only show Next when already done (navigating back) */}
        {phase === "already_done" && (
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
