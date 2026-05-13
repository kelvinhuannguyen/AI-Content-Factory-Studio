"use client";

import { useState, useEffect } from "react";
import { Sparkles, TrendingUp, Pencil, ArrowRight, AlertCircle, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { createProject } from "@/hooks/useProject";
import { useWizardStore } from "@/stores/wizardStore";
import type { StepProps } from "./types";

interface TrendingTopic {
  title: string;
  hook: string;
  rationale: string;
  trend_score: number;
}

export default function StepTopic({ onNext }: StepProps) {
  const { project, setProject, setTopic, topic: savedTopic } = useWizardStore();

  const [mode, setMode] = useState<"manual" | "ai">("manual");
  const [manualTopic, setManualTopic] = useState(savedTopic ?? "");
  const [selected, setSelected] = useState<string | null>(savedTopic ?? null);
  const [topics, setTopics] = useState<TrendingTopic[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  // Create project on first mount if not exists
  useEffect(() => {
    if (!project) {
      createProject("short_video").then((p) =>
        setProject({ id: p.id, title: p.title, production_type: p.production_type, status: p.status, preferred_language: p.preferred_language })
      ).catch(console.error);
    }
  }, [project, setProject]);

  const currentTopic = mode === "manual" ? manualTopic.trim() : selected;
  const canProceed = !!currentTopic;

  const fetchTrending = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.post<{ topics: TrendingTopic[] }>("/topics/trending", {
        genre: "education",
        style: "educational",
        production_type: "short_video",
        language: project?.preferred_language ?? "vi",
      });
      setTopics(res.topics ?? []);
    } catch (e: any) {
      setError(e.message ?? "Không kết nối được API");
    } finally {
      setLoading(false);
    }
  };

  const handleNext = async () => {
    if (!currentTopic) return;
    setCreating(true);
    try {
      setTopic(currentTopic);
      // Update project topic via API
      if (project) {
        await api.patch(`/projects/${project.id}`, {
          topic: currentTopic,
          title: currentTopic.slice(0, 100),
          status: "topic_selected",
        });
      }
      onNext();
    } catch (e) {
      console.error(e);
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h2 className="text-xl font-bold">Chọn chủ đề</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Nhập ý tưởng thủ công hoặc để AI gợi ý xu hướng từ YouTube
        </p>
      </div>

      {/* Mode tabs */}
      <div className="flex rounded-xl border border-border bg-muted p-1">
        {[
          { key: "manual", icon: Pencil,     label: "Nhập thủ công" },
          { key: "ai",     icon: TrendingUp, label: "AI gợi ý xu hướng" },
        ].map(({ key, icon: Icon, label }) => (
          <button
            key={key}
            onClick={() => setMode(key as "manual" | "ai")}
            className={cn(
              "flex flex-1 items-center justify-center gap-2 rounded-lg py-2 text-sm font-medium transition-all",
              mode === key ? "bg-card card-shadow text-foreground" : "text-muted-foreground hover:text-foreground"
            )}
          >
            <Icon className="h-4 w-4" /> {label}
          </button>
        ))}
      </div>

      {mode === "manual" ? (
        <div className="space-y-2">
          <textarea
            value={manualTopic}
            onChange={(e) => { setManualTopic(e.target.value); setSelected(e.target.value); }}
            placeholder="Ví dụ: 5 thói quen buổi sáng giúp tăng năng suất gấp đôi trong 30 ngày..."
            rows={4}
            className="w-full rounded-xl border border-border bg-card px-4 py-3 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 resize-none card-shadow"
          />
          <p className="text-xs text-muted-foreground">{manualTopic.length} ký tự · Mô tả chi tiết giúp AI viết kịch bản tốt hơn</p>
        </div>
      ) : (
        <div className="space-y-3">
          <button
            onClick={fetchTrending}
            disabled={loading}
            className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-primary/50 bg-primary/5 py-3 text-sm font-medium text-primary hover:bg-primary/10 transition-colors disabled:opacity-50"
          >
            {loading
              ? <><div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" /> Đang phân tích xu hướng YouTube...</>
              : <><Sparkles className="h-4 w-4" /> Phân tích xu hướng ngay</>
            }
          </button>

          {error && (
            <div className="flex items-center gap-2 rounded-xl border border-destructive/30 bg-destructive/5 p-3">
              <AlertCircle className="h-4 w-4 text-destructive shrink-0" />
              <p className="text-xs text-destructive">{error}</p>
              <button onClick={fetchTrending} className="ml-auto">
                <RefreshCw className="h-3.5 w-3.5 text-destructive" />
              </button>
            </div>
          )}

          {topics.length > 0 && (
            <div className="space-y-2">
              {topics.map((t) => (
                <button
                  key={t.title}
                  onClick={() => setSelected(t.title)}
                  className={cn(
                    "w-full rounded-xl border p-4 text-left transition-all hover:border-primary/50",
                    selected === t.title ? "border-primary bg-primary/5 dark:bg-primary/10" : "border-border bg-card card-shadow"
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="space-y-1">
                      <p className="text-sm font-semibold text-foreground">{t.title}</p>
                      <p className="text-xs text-muted-foreground">"{t.hook}"</p>
                      <p className="text-[11px] text-muted-foreground/70">{t.rationale}</p>
                    </div>
                    <span className="shrink-0 rounded-full bg-primary/10 px-2.5 py-1 text-xs font-bold text-primary">
                      {t.trend_score}%
                    </span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="flex justify-end pt-2">
        <button
          onClick={handleNext}
          disabled={!canProceed || creating}
          className="flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-40 transition-colors"
        >
          {creating ? <><div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" /> Đang lưu...</> : <>Tiếp theo <ArrowRight className="h-4 w-4" /></>}
        </button>
      </div>
    </div>
  );
}
