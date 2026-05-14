"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Sparkles, ArrowLeft, ArrowRight, Loader2, RefreshCw, Check } from "lucide-react";
import { useSSE } from "@/hooks/useSSE";
import { useWizardStore } from "@/stores/wizardStore";
import type { StepProps } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

type Phase =
  | "waiting"      // LangGraph đang xử lý scene planner
  | "planning"     // scene_planner_node đang chạy
  | "ready"        // scenes sẵn sàng, chờ duyệt
  | "approving"    // đang gửi approve
  | "rejecting"    // đang gửi reject (re-plan)
  | "replanning"   // đã reject, scene planner chạy lại
  | "already_done"; // user quay lại từ bước sau

interface SceneItem {
  id: string;
  scene_number: number;
  title: string;
  description: string;
  video_prompt: string;
  duration_seconds: number;
}

export default function StepSceneBreakdown({ onNext, onBack }: StepProps) {
  const { project } = useWizardStore();
  const projectId = project?.id;

  const [phase, setPhase] = useState<Phase>("waiting");
  const [scenes, setScenes] = useState<SceneItem[]>([]);
  const [saving, setSaving] = useState<string | null>(null);
  const syncedRef = useRef(false);

  async function loadScenes() {
    if (!projectId) return;
    try {
      const res = await fetch(`${BASE}/scenes/${projectId}`);
      if (!res.ok) return;
      const data: SceneItem[] = await res.json();
      if (Array.isArray(data) && data.length > 0 && !("status" in data[0] && (data[0] as any).status?.includes("not_implemented"))) {
        setScenes(data);
      }
    } catch {
      // silent
    }
  }

  async function syncState() {
    if (!projectId) return;
    try {
      const res = await fetch(`${BASE}/pipeline/${projectId}/state`);
      if (!res.ok) return;
      const state = await res.json();

      if (state.paused_at === "scene_review") {
        await loadScenes();
        setPhase("ready");
      } else if (
        state.current_stage === "video_editor" ||
        state.current_stage === "video_validator" ||
        state.paused_at === "video_review" ||
        state.status === "completed"
      ) {
        await loadScenes();
        setPhase("already_done");
      } else if (state.current_stage === "scene_planner") {
        setPhase("planning");
      } else {
        setPhase("waiting");
      }
    } catch {
      setPhase("waiting");
    }
  }

  useEffect(() => {
    if (!projectId || syncedRef.current) return;
    syncedRef.current = true;
    syncState();
  }, [projectId]);

  // SSE handler
  const handleSSE = useCallback((event: any) => {
    const { type, agent, step } = event;

    if (type === "agent_start" && agent === "scene_planner") {
      setPhase("planning");
    }

    if (type === "agent_done" && agent === "scene_planner") {
      loadScenes();
    }

    if (type === "agent_interrupt" && step === "scene_review") {
      loadScenes();
      setPhase("ready");
    }

    if (type === "agent_error" && agent === "scene_planner") {
      setPhase("waiting");
    }
  }, [projectId]);

  useSSE(projectId ?? null, handleSSE);

  async function handleApprove() {
    if (!projectId) return;
    setPhase("approving");
    try {
      await fetch(`${BASE}/pipeline/${projectId}/resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ step: "scene", approved: true }),
      });
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
        body: JSON.stringify({ step: "scene", approved: false }),
      });
      setScenes([]);
      setPhase("replanning");
    } catch {
      setPhase("ready");
    }
  }

  async function handlePromptChange(sceneId: string, newPrompt: string) {
    setScenes((prev) => prev.map((s) => s.id === sceneId ? { ...s, video_prompt: newPrompt } : s));
  }

  async function handlePromptBlur(sceneId: string, prompt: string) {
    setSaving(sceneId);
    try {
      await fetch(`${BASE}/scenes/${sceneId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ video_prompt: prompt }),
      });
    } finally {
      setSaving(null);
    }
  }

  async function handleRegenPrompt(scene: SceneItem) {
    setSaving(scene.id);
    try {
      const res = await fetch(`${BASE}/scenes/${scene.id}/regenerate-prompt`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ character_description: "" }),
      });
      if (res.ok) {
        const updated = await res.json();
        setScenes((prev) => prev.map((s) => s.id === scene.id ? { ...s, video_prompt: updated.video_prompt } : s));
      }
    } finally {
      setSaving(null);
    }
  }

  const totalDuration = scenes.reduce((sum, s) => sum + (s.duration_seconds || 0), 0);
  const isSubmitting = phase === "approving" || phase === "rejecting";

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-xl font-bold">Phân cảnh & Prompt video</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {scenes.length > 0
              ? `${scenes.length} cảnh · ${totalDuration}s tổng thời lượng`
              : phase === "already_done"
              ? "Phân cảnh đã duyệt — bắt đầu tạo video"
              : "LangGraph scene_planner đang phân tích kịch bản thành cảnh quay"}
          </p>
        </div>
      </div>

      {/* Waiting / planning states */}
      {(phase === "waiting" || phase === "planning" || phase === "replanning") && (
        <div className="flex items-center gap-3 rounded-xl border border-primary/20 bg-primary/5 p-4">
          <Loader2 className="h-5 w-5 animate-spin text-primary shrink-0" />
          <div>
            <p className="text-sm font-medium text-primary">
              {phase === "replanning" ? "Đang phân cảnh lại..." : "Đang phân tích kịch bản thành cảnh quay..."}
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">
              Gemini-2.5-flash · Tạo video prompt cho từng cảnh
            </p>
          </div>
        </div>
      )}

      {/* Already done */}
      {phase === "already_done" && scenes.length === 0 && (
        <div className="rounded-xl border border-green-500/30 bg-green-500/5 p-4 flex items-center gap-3">
          <Check className="h-5 w-5 text-green-500 shrink-0" />
          <p className="text-sm font-semibold text-green-700 dark:text-green-400">
            Phân cảnh đã duyệt — video đang được tạo
          </p>
        </div>
      )}

      {/* Scene list */}
      {scenes.length > 0 && (
        <div className="space-y-3">
          {scenes.map((scene) => (
            <div key={scene.id} className="rounded-xl border border-border bg-card overflow-hidden">
              <div className="flex items-center gap-3 px-4 py-2.5 bg-muted/40">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary text-[10px] font-bold text-primary-foreground">
                  {scene.scene_number}
                </span>
                <span className="flex-1 text-sm font-semibold truncate">{scene.title}</span>
                <span className="text-xs text-muted-foreground shrink-0">{scene.duration_seconds}s</span>
              </div>
              <div className="px-4 py-3 space-y-2">
                {scene.description && (
                  <p className="text-xs text-muted-foreground">{scene.description}</p>
                )}
                <div className="relative">
                  <textarea
                    value={scene.video_prompt}
                    onChange={(e) => handlePromptChange(scene.id, e.target.value)}
                    onBlur={(e) => handlePromptBlur(scene.id, e.target.value)}
                    rows={2}
                    placeholder="Video prompt cho AI generation..."
                    className="w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-xs leading-relaxed focus:outline-none focus:ring-2 focus:ring-primary/50 resize-none pr-8"
                    disabled={phase !== "ready" && phase !== "already_done"}
                  />
                  {phase === "ready" && (
                    <button
                      onClick={() => handleRegenPrompt(scene)}
                      disabled={saving === scene.id}
                      className="absolute right-2 top-2 text-muted-foreground hover:text-foreground transition-colors disabled:opacity-40"
                      title="Tạo lại prompt"
                    >
                      {saving === scene.id
                        ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        : <RefreshCw className="h-3.5 w-3.5" />
                      }
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Approve / Reject buttons */}
      {phase === "ready" && scenes.length > 0 && (
        <div className="flex gap-3">
          <button
            onClick={handleReject}
            disabled={isSubmitting}
            className="flex items-center gap-2 rounded-xl border border-border px-4 py-2.5 text-sm font-medium hover:bg-muted transition-colors disabled:opacity-40"
          >
            {phase === "rejecting"
              ? <Loader2 className="h-4 w-4 animate-spin" />
              : <RefreshCw className="h-4 w-4" />
            }
            Phân cảnh lại
          </button>
          <button
            onClick={handleApprove}
            disabled={isSubmitting}
            className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-40 transition-colors"
          >
            {phase === "approving"
              ? <Loader2 className="h-4 w-4 animate-spin" />
              : <Sparkles className="h-4 w-4" />
            }
            Duyệt — Bắt đầu tạo video
          </button>
        </div>
      )}

      <div className="flex justify-between pt-2">
        <button
          onClick={onBack}
          className="flex items-center gap-2 rounded-xl border border-border px-4 py-2.5 text-sm font-medium hover:bg-muted transition-colors"
        >
          <ArrowLeft className="h-4 w-4" /> Quay lại
        </button>

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
