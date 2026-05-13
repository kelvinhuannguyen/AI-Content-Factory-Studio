"use client";

import { useState } from "react";
import { ArrowLeft, ArrowRight, Smartphone, Loader2, User } from "lucide-react";
import { SHORT_DURATIONS, VIDEO_GENRES, VIDEO_STYLES } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { useWizardStore } from "@/stores/wizardStore";
import type { StepProps } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export default function StepConfig({ onNext, onBack }: StepProps) {
  const { project, setConfig, setCharacterConfig } = useWizardStore();
  const [duration, setDuration] = useState<number | null>(null);
  const [genre, setGenre] = useState("");
  const [style, setStyle] = useState("");
  const [characterDescription, setCharacterDescription] = useState("");
  const [characterName, setCharacterName] = useState("");
  const [saving, setSaving] = useState(false);

  const canProceed = duration !== null && genre !== "" && style !== "";

  async function handleNext() {
    if (!canProceed) return;
    setConfig(duration!, genre, style, "9:16");
    setCharacterConfig(characterDescription, characterName);
    if (project?.id) {
      setSaving(true);
      try {
        await fetch(`${BASE}/projects/${project.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ duration_seconds: duration, genre, style }),
        });
      } finally {
        setSaving(false);
      }
    }
    onNext();
  }

  return (
    <div className="mx-auto max-w-2xl space-y-7">
      <div>
        <h2 className="text-xl font-bold">Cấu hình sản xuất</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Chọn thời lượng, thể loại và phong cách video
        </p>
      </div>

      {/* Aspect ratio — auto, display only */}
      <div className="flex items-center gap-3 rounded-xl bg-violet-50 dark:bg-violet-950/30 border border-violet-200/60 dark:border-violet-800/40 px-4 py-3">
        <Smartphone className="h-4 w-4 text-violet-500 shrink-0" />
        <div>
          <p className="text-xs font-semibold text-violet-700 dark:text-violet-300">Tỉ lệ màn hình: 9:16 dọc (tự động)</p>
          <p className="text-xs text-violet-600/70 dark:text-violet-400/70 mt-0.5">Chuẩn TikTok · Reels · YouTube Shorts — không cần chọn</p>
        </div>
      </div>

      {/* Duration */}
      <div className="space-y-3">
        <label className="text-sm font-semibold">Thời lượng</label>
        <div className="grid grid-cols-3 gap-2">
          {SHORT_DURATIONS.map(({ value, label }) => (
            <button
              key={value}
              onClick={() => setDuration(value)}
              className={cn(
                "rounded-xl border py-2.5 text-sm font-medium transition-all",
                duration === value
                  ? "border-primary bg-primary/10 text-primary dark:bg-primary/20"
                  : "border-border bg-card hover:border-primary/40 hover:bg-muted"
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Genre */}
      <div className="space-y-3">
        <label className="text-sm font-semibold">Thể loại nội dung</label>
        <div className="flex flex-wrap gap-2">
          {VIDEO_GENRES.slice(0, 14).map(({ value, label }) => (
            <button
              key={value}
              onClick={() => setGenre(value)}
              className={cn(
                "rounded-full border px-3 py-1 text-xs font-medium transition-all",
                genre === value
                  ? "border-primary bg-primary/10 text-primary dark:bg-primary/20"
                  : "border-border bg-card hover:border-primary/40 hover:bg-muted text-muted-foreground hover:text-foreground"
              )}
            >
              {label}
            </button>
          ))}
        </div>
        <select
          value={genre}
          onChange={(e) => setGenre(e.target.value)}
          className="w-full rounded-xl border border-border bg-card px-3 py-2.5 text-sm text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
        >
          <option value="">— Thể loại khác —</option>
          {VIDEO_GENRES.map(({ value, label }) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
      </div>

      {/* Style */}
      <div className="space-y-3">
        <label className="text-sm font-semibold">Phong cách quay</label>
        <div className="grid grid-cols-3 gap-2">
          {VIDEO_STYLES.map(({ value, label }) => (
            <button
              key={value}
              onClick={() => setStyle(value)}
              className={cn(
                "rounded-xl border px-3 py-2.5 text-xs font-medium transition-all text-center",
                style === value
                  ? "border-primary bg-primary/10 text-primary dark:bg-primary/20"
                  : "border-border bg-card hover:border-primary/40 hover:bg-muted text-muted-foreground hover:text-foreground"
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Character config — collected here so pipeline can use it immediately */}
      <div className="space-y-4 rounded-xl border border-border bg-card p-4">
        <div className="flex items-center gap-2">
          <User className="h-4 w-4 text-primary" />
          <p className="text-sm font-semibold">Nhân vật chính (tuỳ chọn)</p>
        </div>
        <p className="text-xs text-muted-foreground -mt-2">
          AI sẽ tạo 3 biến thể nhân vật ngay sau khi kịch bản được duyệt
        </p>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Mô tả nhân vật</label>
            <textarea
              value={characterDescription}
              onChange={(e) => setCharacterDescription(e.target.value)}
              placeholder="Ví dụ: Nữ 25 tuổi, tóc đen dài, mắt sáng, phong cách hiện đại, thân thiện..."
              rows={2}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 resize-none"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Tên nhân vật</label>
            <input
              type="text"
              value={characterName}
              onChange={(e) => setCharacterName(e.target.value)}
              placeholder="Lan, Minh, Emma... (tuỳ chọn)"
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
            />
          </div>
        </div>
      </div>

      <div className="flex justify-between pt-2">
        <button
          onClick={onBack}
          className="flex items-center gap-2 rounded-xl border border-border px-4 py-2.5 text-sm font-medium hover:bg-muted transition-colors"
        >
          <ArrowLeft className="h-4 w-4" /> Quay lại
        </button>
        <button
          onClick={handleNext}
          disabled={!canProceed || saving}
          className="flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-40 transition-colors"
        >
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
          Bắt đầu viết kịch bản
        </button>
      </div>
    </div>
  );
}
