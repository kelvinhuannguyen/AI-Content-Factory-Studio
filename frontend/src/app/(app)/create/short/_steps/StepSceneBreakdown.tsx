"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Sparkles, ArrowLeft, ArrowRight, Loader2, RefreshCw, Check, Film } from "lucide-react";
import { cn } from "@/lib/utils";
import { useSSE } from "@/hooks/useSSE";
import { useWizardStore } from "@/stores/wizardStore";
import type { StepProps } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

type Phase =
  | "waiting"       // scene_planner / cinematic_decomposer running
  | "shot_ready"    // shot_review INTERRUPT — Trạm 2, waiting for user decision
  | "approving"     // sending approve
  | "rejecting"     // sending reject (re-plan)
  | "replanning"    // rejected, scene_planner running again
  | "already_done"; // user came back from a later step

interface SceneItem {
  id: string;
  scene_number: number;
  title: string;
  description: string;
  video_prompt: string;
  duration_seconds: number;
}

interface ShotItem {
  id: string;
  shot_id: string;
  duration: number;
  prompt: string;
  qc_score: number | null;
  motion_intensity: number | null;
}

export default function StepSceneBreakdown({ onNext, onBack }: StepProps) {
  const { project } = useWizardStore();
  const projectId = project?.id;

  const [phase, setPhase] = useState<Phase>("waiting");
  const [scenes, setScenes] = useState<SceneItem[]>([]);
  const [shots, setShots] = useState<ShotItem[]>([]);
  const [saving, setSaving] = useState<string | null>(null);
  const syncedRef = useRef(false);

  async function loadShots() {
    if (!projectId) return;
    try {
      const res = await fetch(`${BASE}/shots/${projectId}`);
      if (!res.ok) return;
      const data = await res.json();
      if (Array.isArray(data) && data.length > 0) setShots(data);
    } catch { /* silent */ }
  }

  async function loadScenes() {
    if (!projectId) return;
    try {
      const res = await fetch(`${BASE}/scenes/${projectId}`);
      if (!res.ok) return;
      const data: SceneItem[] = await res.json();
      if (Array.isArray(data) && data.length > 0) setScenes(data);
    } catch { /* silent */ }
  }

  async function syncState() {
    if (!projectId) return;
    try {
      const res = await fetch(`${BASE}/pipeline/${projectId}/state`);
      if (!res.ok) return;
      const state = await res.json();

      if (state.paused_at === "shot_review") {
        await loadScenes();
        await loadShots();
        setPhase("shot_ready");
      } else if (
        state.current_stage === "continuity_director" ||
        state.current_stage === "video_editor" ||
        state.current_stage === "video_validator" ||
        state.current_stage === "final_assembler" ||
        state.current_stage === "seo_agent" ||
        state.current_stage === "seo_review" ||
        state.paused_at === "seo_review" ||
        state.status === "completed"
      ) {
        await loadScenes();
        await loadShots();
        setPhase("already_done");
      } else if (
        state.current_stage === "scene_planner" ||
        state.current_stage === "cinematic_decomposer" ||
        state.current_stage === "shot_review"
      ) {
        setPhase("waiting");
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

  const handleSSE = useCallback((event: any) => {
    const { type, agent, step } = event;

    if (type === "agent_start" && (agent === "scene_planner" || agent === "cinematic_decomposer")) {
      setPhase("waiting");
    }

    if (type === "agent_done" && agent === "scene_planner") {
      loadScenes();
    }

    if (type === "agent_done" && agent === "cinematic_decomposer") {
      loadShots();
    }

    if (type === "agent_interrupt" && step === "shot_review") {
      // Trạm 2 interrupt fires
      loadScenes();
      loadShots();
      setPhase("shot_ready");
    }

    if (type === "agent_error" && agent === "scene_planner") {
      setPhase("waiting");
    }
  }, [projectId]);

  useSSE(projectId ?? null, handleSSE);

  async function handleShotApprove() {
    if (!projectId) return;
    setPhase("approving");
    try {
      await fetch(`${BASE}/pipeline/${projectId}/resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ step: "shot_review", approved: true }),
      });
      onNext();
    } catch {
      setPhase("shot_ready");
    }
  }

  async function handleShotReject() {
    if (!projectId) return;
    setPhase("rejecting");
    try {
      await fetch(`${BASE}/pipeline/${projectId}/resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ step: "shot_review", approved: false }),
      });
      setShots([]);
      setScenes([]);
      setPhase("replanning");
    } catch {
      setPhase("shot_ready");
    }
  }

  async function handlePromptChange(sceneId: string, newPrompt: string) {
    setScenes(prev => prev.map(s => s.id === sceneId ? { ...s, video_prompt: newPrompt } : s));
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
        setScenes(prev => prev.map(s => s.id === scene.id ? { ...s, video_prompt: updated.video_prompt } : s));
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
          <h2 className="text-xl font-bold">Phân cảnh & Storyboard</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {shots.length > 0
              ? `${shots.length} shots ≤8s · ${scenes.length} cảnh · ${totalDuration}s tổng thời lượng`
              : scenes.length > 0
              ? `${scenes.length} cảnh · ${totalDuration}s · Đang phân rã thành shots...`
              : phase === "already_done"
              ? "Đã duyệt — video đang được tạo"
              : "LangGraph đang phân tích kịch bản thành cảnh quay và shots"}
          </p>
        </div>
      </div>

      {/* Waiting / planning states */}
      {(phase === "waiting" || phase === "replanning") && (
        <div className="flex items-center gap-3 rounded-xl border border-primary/20 bg-primary/5 p-4">
          <Loader2 className="h-5 w-5 animate-spin text-primary shrink-0" />
          <div>
            <p className="text-sm font-medium text-primary">
              {phase === "replanning" ? "Đang phân cảnh lại..." : "Đang phân tích kịch bản thành shots ≤8s..."}
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">
              scene_planner → cinematic_decomposer → Trạm 2 duyệt
            </p>
          </div>
        </div>
      )}

      {/* Already done */}
      {phase === "already_done" && shots.length === 0 && scenes.length === 0 && (
        <div className="rounded-xl border border-green-500/30 bg-green-500/5 p-4 flex items-center gap-3">
          <Check className="h-5 w-5 text-green-500 shrink-0" />
          <p className="text-sm font-semibold text-green-700 dark:text-green-400">
            Storyboard đã duyệt — video đang được render
          </p>
        </div>
      )}

      {/* Trạm 2 interrupt — shot_ready */}
      {phase === "shot_ready" && shots.length > 0 && (
        <div className="rounded-xl border-2 border-primary/30 bg-primary/5 p-4 space-y-2">
          <div className="flex items-center gap-2">
            <Film className="h-4 w-4 text-primary" />
            <p className="text-sm font-semibold text-primary">
              Trạm 2 — Duyệt Storyboard & Shot List
            </p>
          </div>
          <p className="text-xs text-muted-foreground">
            Kiểm tra {shots.length} shot prompts ≤8s trước khi bắt đầu render video hàng loạt.
          </p>
        </div>
      )}

      {/* Scene list (collapsible context, editable when shot_ready) */}
      {scenes.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Danh sách cảnh</p>
          {scenes.map(scene => (
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
                    onChange={e => handlePromptChange(scene.id, e.target.value)}
                    onBlur={e => handlePromptBlur(scene.id, e.target.value)}
                    rows={2}
                    placeholder="Video prompt cho AI generation..."
                    className="w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-xs leading-relaxed focus:outline-none focus:ring-2 focus:ring-primary/50 resize-none pr-8"
                    disabled={phase !== "already_done"}
                  />
                  {phase === "already_done" && (
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

      {/* Shot breakdown — primary Trạm 2 content */}
      {shots.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <Film className="h-4 w-4 text-primary" />
            <span>Cinematic Decomposer — {shots.length} shots ≤8s</span>
          </div>
          {(() => {
            const grouped = shots.reduce<Record<string, ShotItem[]>>((acc, s) => {
              const prefix = (s.shot_id || "").split("_")[0] || "SC";
              if (!acc[prefix]) acc[prefix] = [];
              acc[prefix].push(s);
              return acc;
            }, {});
            return Object.entries(grouped).map(([prefix, grpShots]) => (
              <div key={prefix} className="rounded-lg border border-border overflow-hidden">
                <div className="px-3 py-1.5 bg-muted/50 text-xs font-mono text-muted-foreground font-semibold">
                  {prefix} — {grpShots.length} shot{grpShots.length > 1 ? "s" : ""}
                </div>
                {grpShots.map(shot => (
                  <div key={shot.id} className="px-3 py-2 border-t border-border flex items-start gap-3 text-xs">
                    <span className="font-mono text-muted-foreground w-20 shrink-0">{shot.shot_id}</span>
                    <span className="text-muted-foreground w-8 shrink-0">{shot.duration}s</span>
                    <span className="flex-1 line-clamp-2 text-foreground/80">{shot.prompt}</span>
                    {shot.qc_score !== null && (
                      <span className={cn("shrink-0 font-medium", shot.qc_score >= 8 ? "text-green-600" : "text-amber-600")}>
                        {shot.qc_score.toFixed(1)}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            ));
          })()}
        </div>
      )}

      {/* Trạm 2 — Approve / Reject buttons */}
      {phase === "shot_ready" && shots.length > 0 && (
        <div className="flex gap-3">
          <button
            onClick={handleShotReject}
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
            onClick={handleShotApprove}
            disabled={isSubmitting}
            className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-40 transition-colors"
          >
            {phase === "approving"
              ? <Loader2 className="h-4 w-4 animate-spin" />
              : <Sparkles className="h-4 w-4" />
            }
            Duyệt — Bắt đầu Render
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
