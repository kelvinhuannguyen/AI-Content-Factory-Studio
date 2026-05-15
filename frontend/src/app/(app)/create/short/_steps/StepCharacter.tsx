"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { Check, ArrowLeft, ArrowRight, RefreshCw, Loader2, User, Sparkles, ChevronDown, ChevronUp } from "lucide-react";
import { cn } from "@/lib/utils";
import { useSSE } from "@/hooks/useSSE";
import { useWizardStore } from "@/stores/wizardStore";
import type { StepProps } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

type Phase =
  | "waiting"       // LangGraph chưa trigger character_designer
  | "analyzing"     // IP Architect đang đọc kịch bản
  | "generating"    // Đang tạo ảnh
  | "reviewing"     // Reviewer Agent đang kiểm tra chất lượng
  | "ready"         // Tất cả nhân vật ready, chờ duyệt
  | "approving"
  | "already_done"; // Nhân vật đã duyệt, pipeline tiếp tục

interface CharacterDesign {
  id: string;
  character_index: number;
  ref_id: string;
  name: string | null;
  role: "main" | "supporting" | null;
  visual_identity_string: string | null;
  physical_dna: Record<string, string> | null;
  color_palette: Record<string, string> | null;
  image_url: string | null;
  sheet_url: string | null;
  user_prompt_addition: string;
  status: "pending" | "generating" | "ready" | "error";
}

export default function StepCharacter({ onNext, onBack }: StepProps) {
  const { project } = useWizardStore();
  const projectId = project?.id ?? null;

  const [phase, setPhase] = useState<Phase>("waiting");
  const [characters, setCharacters] = useState<CharacterDesign[]>([]);
  const [expandedCards, setExpandedCards] = useState<Record<string, boolean>>({});
  const [regenerating, setRegenerating] = useState<Record<string, boolean>>({});
  const [continueLoading, setContinueLoading] = useState(false);
  const syncedRef = useRef(false);

  // ── Data loading ──────────────────────────────────────────────────────

  async function loadCharacters() {
    if (!projectId) return;
    try {
      const res = await fetch(`${BASE}/characters/${projectId}`);
      if (!res.ok) return;
      const data: any[] = await res.json();
      if (data.length > 0) {
        setCharacters(data.map((c) => ({
          id: c.id,
          character_index: c.character_index ?? 0,
          ref_id: c.ref_id ?? `#CHAR_0${(c.character_index ?? 0) + 1}`,
          name: c.name ?? null,
          role: c.character_role ?? (c.character_index === 0 ? "main" : "supporting"),
          visual_identity_string: c.visual_identity_string ?? null,
          physical_dna: c.physical_dna ?? null,
          color_palette: c.color_palette ?? null,
          image_url: c.image_url ?? null,
          sheet_url: c.sheet_url ?? null,
          user_prompt_addition: c.user_prompt_addition ?? "",
          status: c.image_url ? "ready" : "pending",
        })));
      }
    } catch {
      // silent
    }
  }

  // ── Sync pipeline state on mount ─────────────────────────────────────

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
        state.current_stage === "character_designer" ||
        state.current_stage === "character_scorer" ||  // scorer running vision API — show as generating
        state.current_stage === "character_review"
      ) {
        setPhase("generating");
        await loadCharacters();
      } else if (
        state.current_stage === "scene_planner" ||
        state.current_stage === "cinematic_decomposer" ||
        state.current_stage === "shot_review" ||
        state.current_stage === "continuity_director" ||
        state.current_stage === "scene_review" ||
        state.current_stage === "video_editor" ||
        state.current_stage === "video_validator" ||
        state.current_stage === "seo_agent" ||
        state.current_stage === "seo_review" ||
        state.paused_at === "shot_review" ||
        state.paused_at === "video_review" ||
        state.paused_at === "seo_review" ||
        state.status === "completed"
      ) {
        await loadCharacters();
        setPhase("already_done");
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

  // ── SSE handler ───────────────────────────────────────────────────────

  const handleSSE = useCallback((event: any) => {
    const { type, agent, step } = event;

    if (type === "agent_start" && agent === "character_designer") {
      if (event.character_count !== undefined) {
        setPhase("generating");
      } else {
        setPhase("analyzing");
      }
    }

    if (type === "agent_start" && agent === "character_scorer") {
      setPhase("reviewing");
    }

    if (type === "character_progress") {
      const refId: string = event.ref_id ?? `#CHAR_0${(event.character_index ?? 0) + 1}`;
      setCharacters((prev) => {
        const exists = prev.find((c) => c.ref_id === refId);
        if (exists) {
          return prev.map((c) => c.ref_id === refId ? { ...c, status: "generating" } : c);
        }
        return [...prev, {
          id: "",
          character_index: event.character_index ?? 0,
          ref_id: refId,
          name: event.name ?? null,
          role: event.role ?? "main",
          visual_identity_string: null,
          physical_dna: null,
          color_palette: null,
          image_url: null,
          sheet_url: null,
          user_prompt_addition: "",
          status: "generating",
        }];
      });
      setPhase("generating");
    }

    if (type === "character_ready") {
      const refId: string = event.ref_id ?? `#CHAR_0${(event.character_index ?? 0) + 1}`;
      setCharacters((prev) => prev.map((c) =>
        c.ref_id === refId
          ? { ...c, id: event.character_id ?? c.id, image_url: event.result_url ?? c.image_url, status: "ready" }
          : c
      ));
      setRegenerating((prev) => ({ ...prev, [refId]: false }));
    }

    if (type === "character_error") {
      const refId: string = event.ref_id ?? `#CHAR_0${(event.character_index ?? 0) + 1}`;
      setCharacters((prev) => prev.map((c) =>
        c.ref_id === refId ? { ...c, status: "error" } : c
      ));
      setRegenerating((prev) => ({ ...prev, [refId]: false }));
    }

    if (type === "agent_done" && agent === "character_designer") {
      loadCharacters();
    }

    // Reviewer Agent scoring result
    if (type === "agent_done" && agent === "character_scorer") {
      if (event.will_retry) {
        // Score < 8 → auto-retry: reset failing characters to "generating"
        const briefs: Record<string, string> = event.correction_briefs ?? {};
        if (Object.keys(briefs).length > 0) {
          setCharacters((prev) => prev.map((c) =>
            briefs[c.ref_id] !== undefined
              ? { ...c, status: "generating", image_url: null }
              : c
          ));
        }
        setPhase("generating");
      }
      // If not retrying: character_review interrupt will fire next → stays in generating until then
    }

    if (type === "agent_interrupt" && step === "character_review") {
      loadCharacters();
      setPhase("ready");
    }
  }, [projectId]);

  useSSE(projectId, handleSSE);

  // ── Actions ───────────────────────────────────────────────────────────

  async function handleApproveAll() {
    if (!projectId) return;
    setPhase("approving");
    try {
      await fetch(`${BASE}/pipeline/${projectId}/resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ step: "character", approved: true }),
      });
      onNext();
    } catch {
      setPhase("ready");
    }
  }

  async function handleRegenerateAll() {
    if (!projectId) return;
    try {
      await fetch(`${BASE}/pipeline/${projectId}/resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ step: "character", approved: false }),
      });
      setCharacters([]);
      setPhase("generating");
    } catch {
      // silent
    }
  }

  async function handleRegenerateOne(refId: string) {
    if (!projectId) return;
    const char = characters.find((c) => c.ref_id === refId);
    if (!char) return;

    setRegenerating((prev) => ({ ...prev, [refId]: true }));
    setCharacters((prev) => prev.map((c) =>
      c.ref_id === refId ? { ...c, status: "generating", image_url: null } : c
    ));

    try {
      await fetch(`${BASE}/characters/${projectId}/regenerate/${encodeURIComponent(refId)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_prompt_addition: char.user_prompt_addition }),
      });
    } catch {
      setRegenerating((prev) => ({ ...prev, [refId]: false }));
      setCharacters((prev) => prev.map((c) =>
        c.ref_id === refId ? { ...c, status: "error" } : c
      ));
    }
  }

  async function handleContinue() {
    if (!projectId) return;
    setContinueLoading(true);
    try {
      await fetch(`${BASE}/pipeline/${projectId}/continue`, { method: "POST" });
      setPhase("generating");
    } catch { /* silent */ } finally {
      setContinueLoading(false);
    }
  }

  function handleUserInputChange(refId: string, value: string) {
    setCharacters((prev) => prev.map((c) =>
      c.ref_id === refId ? { ...c, user_prompt_addition: value } : c
    ));
  }

  function toggleExpand(refId: string) {
    setExpandedCards((prev) => ({ ...prev, [refId]: !prev[refId] }));
  }

  // ── Derived state ─────────────────────────────────────────────────────

  const allReady = characters.length > 0 && characters.every((c) => c.status === "ready");
  const isSubmitting = phase === "approving";

  // ── Render ────────────────────────────────────────────────────────────

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h2 className="text-xl font-bold">Thiết kế nhân vật</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {phase === "waiting" && "Chờ pipeline kích hoạt thiết kế nhân vật..."}
          {phase === "analyzing" && "AI đang phân tích kịch bản để xác định nhân vật..."}
          {phase === "generating" && `Đang thiết kế ${characters.length > 0 ? characters.length : ""} nhân vật...`}
          {phase === "reviewing" && "Reviewer Agent đang kiểm tra chất lượng (Senior Art Director AI)..."}
          {phase === "ready" && `${characters.length} nhân vật đã sẵn sàng — kiểm tra và duyệt`}
          {phase === "approving" && "Đang gửi xác nhận..."}
          {phase === "already_done" && "Nhân vật đã duyệt — pipeline đang tiếp tục"}
        </p>
      </div>

      {/* Waiting / Analyzing / Reviewing */}
      {(phase === "waiting" || phase === "analyzing" || phase === "reviewing") && (
        <div className="flex items-start gap-3 rounded-xl border border-primary/20 bg-primary/5 p-4">
          <Loader2 className="h-5 w-5 animate-spin text-primary shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-primary">
              {phase === "analyzing"
                ? "IP Architect đang phân tích kịch bản..."
                : phase === "reviewing"
                ? "Reviewer Agent đang kiểm tra chất lượng nhân vật..."
                : "Chờ pipeline kích hoạt..."}
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">
              {phase === "analyzing"
                ? "Xác định nhân vật, thiết kế VIS + Physical DNA + Color Palette"
                : phase === "reviewing"
                ? "Senior Art Director AI: kiểm tra Character Consistency, Script Fidelity, Technical Quality"
                : "LangGraph sẽ tự động kích hoạt sau khi kịch bản được duyệt"}
            </p>
            {phase === "waiting" && (
              <button
                onClick={handleContinue}
                disabled={continueLoading}
                className="mt-3 flex items-center gap-1.5 rounded-lg border border-primary/30 bg-background px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/5 transition-colors disabled:opacity-40"
              >
                {continueLoading
                  ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  : <RefreshCw className="h-3.5 w-3.5" />}
                Tiếp tục pipeline (nếu bị dừng)
              </button>
            )}
          </div>
        </div>
      )}

      {/* 0 characters (narration-only script) + ready */}
      {phase === "ready" && characters.length === 0 && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">
          <p className="text-sm font-semibold text-amber-700 dark:text-amber-400">
            Kịch bản không có nhân vật cụ thể (dạng narration)
          </p>
          <p className="text-xs text-muted-foreground mt-1">Tiếp tục mà không cần thiết kế nhân vật.</p>
        </div>
      )}

      {/* Already done */}
      {phase === "already_done" && (
        <div className="rounded-xl border border-green-500/30 bg-green-500/5 p-4 flex items-center gap-3">
          <Check className="h-5 w-5 text-green-500 shrink-0" />
          <div>
            <p className="text-sm font-semibold text-green-700 dark:text-green-400">
              {characters.length > 0
                ? `${characters.length} nhân vật đã được duyệt`
                : "Nhân vật đã được duyệt"}
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">Pipeline đang tiếp tục ở bước phân cảnh</p>
          </div>
        </div>
      )}

      {/* Character cards */}
      {characters.length > 0 && (
        <div className="space-y-4">
          {characters.map((char) => (
            <CharacterCard
              key={char.ref_id}
              char={char}
              isExpanded={!!expandedCards[char.ref_id]}
              isRegenerating={!!regenerating[char.ref_id]}
              canEdit={phase === "ready"}
              onToggleExpand={() => toggleExpand(char.ref_id)}
              onUserInputChange={(val) => handleUserInputChange(char.ref_id, val)}
              onRegenerate={() => handleRegenerateOne(char.ref_id)}
            />
          ))}
        </div>
      )}

      {/* Nav buttons */}
      <div className="flex justify-between pt-2">
        <button
          onClick={onBack}
          className="flex items-center gap-2 rounded-xl border border-border px-4 py-2.5 text-sm font-medium hover:bg-muted transition-colors"
        >
          <ArrowLeft className="h-4 w-4" /> Quay lại
        </button>

        <div className="flex gap-2">
          {phase === "ready" && characters.length > 0 && (
            <button
              onClick={handleRegenerateAll}
              disabled={isSubmitting}
              className="flex items-center gap-2 rounded-xl border border-border px-4 py-2.5 text-sm font-medium hover:bg-muted transition-colors disabled:opacity-40"
            >
              <RefreshCw className="h-4 w-4" /> Tạo lại tất cả
            </button>
          )}

          {phase === "ready" && (
            <button
              onClick={handleApproveAll}
              disabled={isSubmitting || (!allReady && characters.length > 0)}
              className="flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-40 transition-colors"
            >
              {isSubmitting
                ? <Loader2 className="h-4 w-4 animate-spin" />
                : <Check className="h-4 w-4" />
              }
              Duyệt tất cả nhân vật
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
    </div>
  );
}


// ── CharacterCard sub-component ───────────────────────────────────────────

interface CharacterCardProps {
  char: CharacterDesign;
  isExpanded: boolean;
  isRegenerating: boolean;
  canEdit: boolean;
  onToggleExpand: () => void;
  onUserInputChange: (val: string) => void;
  onRegenerate: () => void;
}

function CharacterCard({
  char,
  isExpanded,
  isRegenerating,
  canEdit,
  onToggleExpand,
  onUserInputChange,
  onRegenerate,
}: CharacterCardProps) {
  const roleLabel = char.role === "main" ? "Nhân vật chính" : "Nhân vật phụ";
  const roleBadgeClass = char.role === "main"
    ? "bg-primary/10 text-primary"
    : "bg-muted text-muted-foreground";

  return (
    <div className={cn(
      "rounded-xl border-2 overflow-hidden transition-all",
      char.status === "ready" ? "border-border" : "border-border/50 opacity-80"
    )}>
      {/* Header row */}
      <div className="flex items-center gap-3 px-4 py-3 bg-card">
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary">
          {char.character_index + 1}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-muted-foreground">{char.ref_id}</span>
            <span className={cn("rounded px-1.5 py-0.5 text-[10px] font-semibold", roleBadgeClass)}>
              {roleLabel}
            </span>
          </div>
          <p className="text-sm font-semibold truncate">{char.name || char.ref_id}</p>
        </div>
        {char.status === "ready" && (
          <button
            onClick={onToggleExpand}
            className="shrink-0 text-muted-foreground hover:text-foreground transition-colors"
          >
            {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>
        )}
      </div>

      {/* Image + info row */}
      <div className="flex gap-4 px-4 py-3 bg-background/50">
        {/* Image */}
        <div className="h-28 w-20 shrink-0 rounded-lg overflow-hidden bg-muted flex items-center justify-center border border-border">
          {char.status === "ready" && char.image_url ? (
            <img
              src={char.image_url}
              alt={char.name || char.ref_id}
              className="h-full w-full object-cover"
            />
          ) : char.status === "generating" || isRegenerating ? (
            <div className="flex flex-col items-center gap-1">
              <Loader2 className="h-6 w-6 animate-spin text-primary/60" />
              <span className="text-[10px] text-muted-foreground">Đang tạo...</span>
            </div>
          ) : char.status === "error" ? (
            <div className="text-center px-1">
              <span className="text-base">⚠️</span>
              <p className="text-[10px] text-destructive mt-1">Lỗi</p>
            </div>
          ) : (
            <User className="h-10 w-10 text-muted-foreground/20" />
          )}
        </div>

        {/* VIS summary */}
        <div className="flex-1 min-w-0 space-y-2">
          {char.visual_identity_string ? (
            <p className="text-xs text-muted-foreground leading-relaxed line-clamp-3">
              {char.visual_identity_string}
            </p>
          ) : char.status === "generating" ? (
            <p className="text-xs text-muted-foreground italic">Đang thiết kế nhân vật...</p>
          ) : null}

          {/* DNA chips */}
          {char.physical_dna && isExpanded && (
            <div className="flex flex-wrap gap-1 mt-1">
              {Object.entries(char.physical_dna)
                .filter(([, v]) => v && v !== "none")
                .slice(0, 6)
                .map(([k, v]) => (
                  <span key={k} className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                    {v}
                  </span>
                ))}
            </div>
          )}

          {/* Color palette */}
          {char.color_palette && isExpanded && (
            <div className="flex items-center gap-1.5 mt-1">
              {["primary", "secondary", "accent"].map((key) =>
                char.color_palette?.[key] ? (
                  <div
                    key={key}
                    className="h-4 w-4 rounded-full border border-border"
                    style={{ backgroundColor: char.color_palette[key] }}
                    title={`${key}: ${char.color_palette[key]}`}
                  />
                ) : null
              )}
              {char.color_palette.theory_note && (
                <span className="text-[10px] text-muted-foreground truncate">{char.color_palette.theory_note}</span>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Customization input (only when ready + editable) */}
      {canEdit && char.status === "ready" && (
        <div className="px-4 pb-3 space-y-2">
          <label className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <Sparkles className="h-3 w-3" /> Thêm ý tưởng của bạn
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={char.user_prompt_addition}
              onChange={(e) => onUserInputChange(e.target.value)}
              placeholder="VD: thêm kính gọng vàng, mặc áo dài đỏ, tóc có highlights..."
              className="flex-1 rounded-lg border border-border bg-background px-3 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-primary/50"
              disabled={isRegenerating}
            />
            <button
              onClick={onRegenerate}
              disabled={isRegenerating}
              className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium hover:bg-muted transition-colors disabled:opacity-40 shrink-0"
            >
              {isRegenerating
                ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                : <RefreshCw className="h-3.5 w-3.5" />
              }
              Tạo lại
            </button>
          </div>
        </div>
      )}

      {/* Error state retry */}
      {canEdit && char.status === "error" && (
        <div className="px-4 pb-3">
          <button
            onClick={onRegenerate}
            disabled={isRegenerating}
            className="flex items-center gap-1.5 text-xs text-destructive hover:underline disabled:opacity-40"
          >
            <RefreshCw className="h-3 w-3" /> Thử lại
          </button>
        </div>
      )}
    </div>
  );
}
