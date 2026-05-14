"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { Check, ArrowLeft, ArrowRight, User, RefreshCw, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useSSE } from "@/hooks/useSSE";
import { useWizardStore } from "@/stores/wizardStore";
import type { StepProps } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

type Phase =
  | "waiting"       // LangGraph đang xử lý character designer
  | "generating"    // Celery đang tạo ảnh
  | "ready"         // characters sẵn sàng, chờ chọn
  | "selecting"     // đang gửi resume
  | "rejecting"     // đang gửi reject
  | "already_done"; // user quay lại từ bước sau

interface CharacterVariant {
  id: string;
  variant_index: number;
  image_url?: string;
  name?: string;
  description?: string;
  status: "pending" | "generating" | "ready" | "error";
}

export default function StepCharacter({ onNext, onBack }: StepProps) {
  const { project, setCharacterId } = useWizardStore();
  const projectId = project?.id ?? null;

  const [phase, setPhase] = useState<Phase>("waiting");
  const [variants, setVariants] = useState<CharacterVariant[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const syncedRef = useRef(false);

  // Load characters from DB
  async function loadCharacters() {
    if (!projectId) return;
    try {
      const res = await fetch(`${BASE}/characters/${projectId}`);
      if (!res.ok) return;
      const data: any[] = await res.json();
      if (data.length > 0) {
        setVariants(data.map((c) => ({
          id: c.id,
          variant_index: c.variant_index,
          image_url: c.image_url ?? undefined,
          name: c.name,
          description: c.description,
          status: "ready" as const,
        })));
        // Pre-select already-selected character
        const selected = data.find((c) => c.is_selected);
        if (selected) setSelectedId(selected.id);
      }
    } catch {
      // silent
    }
  }

  // Sync with pipeline state on mount
  async function syncState() {
    if (!projectId) return;
    try {
      const res = await fetch(`${BASE}/pipeline/${projectId}/state`);
      if (!res.ok) return;
      const state = await res.json();

      if (state.paused_at === "character_review") {
        await loadCharacters();
        setPhase("ready");
      } else if (
        state.current_stage === "scene_planner" ||
        state.current_stage === "scene_review" ||
        state.current_stage === "video_editor" ||
        state.current_stage === "video_validator" ||
        state.paused_at === "video_review" ||
        state.status === "completed"
      ) {
        await loadCharacters();
        setPhase("already_done");
      } else if (state.current_stage === "character_designer") {
        setPhase("generating");
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

    if (type === "agent_start" && agent === "character_designer") {
      setPhase("generating");
    }

    if (type === "character_progress") {
      const idx = event.variant_index ?? 0;
      setVariants((prev) => {
        // Always maintain a dense array of 3 — no undefined holes
        const base: CharacterVariant[] = Array.from({ length: 3 }, (_, i) =>
          prev[i] ?? { id: "", variant_index: i, status: "pending" as const }
        );
        base[idx] = { ...base[idx], status: "generating" };
        return base;
      });
    }

    if (type === "character_ready") {
      const idx = event.variant_index ?? 0;
      setVariants((prev) => {
        const base: CharacterVariant[] = Array.from({ length: 3 }, (_, i) =>
          prev[i] ?? { id: "", variant_index: i, status: "pending" as const }
        );
        base[idx] = {
          id: event.character_id ?? event.task_id ?? "",
          variant_index: idx,
          image_url: event.result_url ?? undefined,
          status: "ready",
        };
        return base;
      });
    }

    if (type === "character_error") {
      const idx = event.variant_index ?? 0;
      setVariants((prev) => {
        const base: CharacterVariant[] = Array.from({ length: 3 }, (_, i) =>
          prev[i] ?? { id: "", variant_index: i, status: "pending" as const }
        );
        base[idx] = { ...base[idx], status: "error" };
        return base;
      });
    }

    if (type === "agent_interrupt" && step === "character_review") {
      // LangGraph paused — load from DB to get correct IDs
      loadCharacters();
      setPhase("ready");
    }

    if (type === "agent_done" && agent === "character_designer") {
      loadCharacters();
    }
  }, [projectId]);

  useSSE(projectId, handleSSE);

  async function handleSelect(variantId: string) {
    if (!variantId || phase === "selecting") return;
    setSelectedId(variantId);
  }

  async function handleApprove() {
    if (!selectedId || !projectId) return;
    setPhase("selecting");
    try {
      await fetch(`${BASE}/pipeline/${projectId}/resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ step: "character", approved: true, selected_character_id: selectedId }),
      });
      setCharacterId(selectedId);
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
        body: JSON.stringify({ step: "character", approved: false }),
      });
      setVariants([]);
      setSelectedId(null);
      setPhase("generating");
    } catch {
      setPhase("ready");
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  const isSubmitting = phase === "selecting" || phase === "rejecting";

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h2 className="text-xl font-bold">Thiết kế nhân vật</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {phase === "waiting" || phase === "generating"
            ? "AI đang tạo 3 biến thể nhân vật — Celery + Kling image generation"
            : phase === "already_done"
            ? "Nhân vật đã được chọn — tiếp tục pipeline"
            : "Chọn 1 biến thể để tiếp tục"}
        </p>
      </div>

      {/* Waiting for LangGraph to trigger character designer */}
      {phase === "waiting" && (
        <div className="flex items-center gap-3 rounded-xl border border-primary/20 bg-primary/5 p-4">
          <Loader2 className="h-5 w-5 animate-spin text-primary shrink-0" />
          <div>
            <p className="text-sm font-medium text-primary">Pipeline đang chuẩn bị tạo nhân vật...</p>
            <p className="text-xs text-muted-foreground mt-0.5">LangGraph sẽ tự động kích hoạt sau khi kịch bản được duyệt</p>
          </div>
        </div>
      )}

      {/* Generating state with variant placeholders */}
      {phase === "generating" && variants.length === 0 && (
        <div className="flex items-center gap-3 rounded-xl border border-primary/20 bg-primary/5 p-4">
          <Loader2 className="h-5 w-5 animate-spin text-primary shrink-0" />
          <div>
            <p className="text-sm font-medium text-primary">Đang tạo 3 biến thể nhân vật...</p>
            <p className="text-xs text-muted-foreground mt-0.5">Celery + flux-1.1-ultra · Khoảng 2-3 phút</p>
          </div>
        </div>
      )}

      {/* Already done */}
      {phase === "already_done" && (
        <div className="rounded-xl border border-green-500/30 bg-green-500/5 p-4 flex items-center gap-3">
          <Check className="h-5 w-5 text-green-500 shrink-0" />
          <div>
            <p className="text-sm font-semibold text-green-700 dark:text-green-400">Nhân vật đã được chọn</p>
            <p className="text-xs text-muted-foreground mt-0.5">Pipeline đang tiếp tục ở bước phân cảnh</p>
          </div>
        </div>
      )}

      {/* Variants grid */}
      {variants.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {phase === "already_done" ? "Biến thể đã tạo" : "Chọn 1 biến thể"}
            </p>
            {phase === "ready" && (
              <button
                onClick={handleReject}
                disabled={isSubmitting}
                className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors disabled:opacity-40"
              >
                <RefreshCw className="h-3.5 w-3.5" /> Tạo lại bộ khác
              </button>
            )}
          </div>

          <div className="grid grid-cols-3 gap-4">
            {variants.filter((v): v is CharacterVariant => v != null).map((v, i) => (
              <button
                key={v.id || i}
                onClick={() => phase === "ready" && v.status === "ready" && handleSelect(v.id)}
                disabled={phase !== "ready" || v.status !== "ready" || isSubmitting}
                className={cn(
                  "relative flex flex-col overflow-hidden rounded-xl border-2 transition-all",
                  selectedId === v.id && v.id
                    ? "border-primary shadow-md"
                    : "border-border hover:border-primary/40",
                  (phase !== "ready" || v.status !== "ready") && "opacity-70 cursor-default"
                )}
              >
                <div className="flex h-36 items-center justify-center bg-muted relative overflow-hidden">
                  {v.status === "ready" && v.image_url ? (
                    <img src={v.image_url} alt={`Biến thể ${v.variant_index + 1}`} className="h-full w-full object-cover" />
                  ) : v.status === "generating" ? (
                    <div className="flex flex-col items-center gap-2">
                      <Loader2 className="h-8 w-8 animate-spin text-primary/60" />
                      <span className="text-xs text-muted-foreground">Đang tạo...</span>
                    </div>
                  ) : v.status === "error" ? (
                    <div className="flex flex-col items-center gap-1 text-center px-2">
                      <span className="text-lg">⚠️</span>
                      <span className="text-xs text-destructive">Lỗi tạo ảnh</span>
                    </div>
                  ) : (
                    <User className="h-14 w-14 text-muted-foreground/20" />
                  )}

                  {selectedId === v.id && v.id && (
                    <div className="absolute right-2 top-2 flex h-6 w-6 items-center justify-center rounded-full bg-primary shadow">
                      <Check className="h-3.5 w-3.5 text-primary-foreground" />
                    </div>
                  )}
                </div>
                <div className="p-2.5 text-left bg-card">
                  <p className="text-xs font-semibold">Biến thể {v.variant_index + 1}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {v.status === "ready"
                      ? selectedId === v.id ? "Đã chọn" : "Click để chọn"
                      : v.status === "generating" ? "Đang xử lý..."
                      : v.status === "error" ? "Lỗi"
                      : "Chờ..."}
                  </p>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="flex justify-between pt-2">
        <button
          onClick={onBack}
          className="flex items-center gap-2 rounded-xl border border-border px-4 py-2.5 text-sm font-medium hover:bg-muted transition-colors"
        >
          <ArrowLeft className="h-4 w-4" /> Quay lại
        </button>

        {phase === "ready" && (
          <button
            onClick={handleApprove}
            disabled={!selectedId || isSubmitting}
            className="flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-40 transition-colors"
          >
            {phase === "selecting"
              ? <Loader2 className="h-4 w-4 animate-spin" />
              : <Check className="h-4 w-4" />
            }
            Duyệt nhân vật này
          </button>
        )}

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
