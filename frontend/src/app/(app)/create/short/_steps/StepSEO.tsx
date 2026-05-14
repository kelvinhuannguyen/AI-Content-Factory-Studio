"use client";

import { useState, useEffect, useRef } from "react";
import {
  Sparkles, Check, ArrowLeft, ArrowRight,
  ImageIcon, Loader2, RefreshCw, X, Plus
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useWizardStore } from "@/stores/wizardStore";
import type { StepProps } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

interface SeoData {
  id: string;
  title_variants: string[];
  description: string;
  tags: string[];
  thumbnail_url: string | null;
  thumbnail_r2_key: string | null;
}

export default function StepSEO({ onNext, onBack }: StepProps) {
  const { project } = useWizardStore();
  const projectId = project?.id;

  const [seo, setSeo] = useState<SeoData | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedTitle, setSelectedTitle] = useState(0);
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [newTag, setNewTag] = useState("");
  const [thumbLoading, setThumbLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [approved, setApproved] = useState(false);
  const [pausedAt, setPausedAt] = useState<string | null>(null);
  const [reviewSubmitting, setReviewSubmitting] = useState(false);

  // Load existing SEO + pipeline state on mount
  useEffect(() => {
    if (!projectId) return;
    // Check pipeline state for seo_review interrupt
    fetch(`${BASE}/pipeline/${projectId}/state`)
      .then(r => r.ok ? r.json() : null)
      .then(state => { if (state?.paused_at) setPausedAt(state.paused_at); })
      .catch(() => {});
    // Load SEO data
    fetch(`${BASE}/seo/${projectId}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data && !data.status?.includes("not_implemented")) {
          hydrate(data);
        }
      })
      .catch(() => {});
  }, [projectId]);

  async function handleSeoApprove(pkg: "a" | "b") {
    if (!projectId) return;
    setReviewSubmitting(true);
    try {
      await fetch(`${BASE}/pipeline/${projectId}/resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ step: "seo_review", approved: true, selected_package: pkg }),
      });
      setPausedAt(null);
      onNext();
    } catch { /* silent */ } finally {
      setReviewSubmitting(false);
    }
  }

  async function handleSeoRedo() {
    if (!projectId) return;
    setReviewSubmitting(true);
    try {
      await fetch(`${BASE}/pipeline/${projectId}/resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ step: "seo_review", approved: false }),
      });
      setSeo(null);
      setPausedAt("seo_agent");
    } catch { /* silent */ } finally {
      setReviewSubmitting(false);
    }
  }

  function hydrate(data: SeoData) {
    setSeo(data);
    setSelectedTitle(0);
    setDescription(data.description || "");
    setTags(data.tags || []);
    setApproved(false);
  }

  async function handleGenerate() {
    if (!projectId) return;
    setLoading(true);
    setSeo(null);
    setApproved(false);
    try {
      const res = await fetch(`${BASE}/seo/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId }),
      });
      if (res.ok) hydrate(await res.json());
    } finally {
      setLoading(false);
    }
  }

  async function handleGenerateThumbnail() {
    if (!projectId) return;
    setThumbLoading(true);
    try {
      const res = await fetch(`${BASE}/seo/${projectId}/thumbnail`, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        setSeo(prev => prev ? { ...prev, thumbnail_url: data.thumbnail_url, thumbnail_r2_key: data.thumbnail_r2_key } : prev);
      }
    } finally {
      setThumbLoading(false);
    }
  }

  async function saveEdits() {
    if (!projectId || !seo) return;
    setSaving(true);
    try {
      const res = await fetch(`${BASE}/seo/${projectId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          selected_title_index: selectedTitle,
          description,
          tags,
        }),
      });
      if (res.ok) setSeo(await res.json());
    } finally {
      setSaving(false);
    }
  }

  function removeTag(tag: string) {
    setTags(prev => prev.filter(t => t !== tag));
  }

  function addTag() {
    const t = newTag.trim().replace(/^#/, "");
    if (t && !tags.includes(t)) setTags(prev => [...prev, t]);
    setNewTag("");
  }

  const canProceed = approved && seo !== null;
  const charCount = description.length;

  // A/B package split: first 3 titles = pkg A, last 3 = pkg B
  const titlesA = seo ? seo.title_variants.slice(0, 3) : [];
  const titlesB = seo ? seo.title_variants.slice(3, 6) : [];

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      {/* SEO Review interrupt panel */}
      {pausedAt === "seo_review" && seo && (
        <div className="rounded-xl border-2 border-primary/40 bg-primary/5 p-4 space-y-3">
          <p className="text-sm font-semibold text-primary">Duyệt Gói SEO A/B — chọn gói để tiếp tục</p>
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-lg border border-green-500/40 bg-green-500/5 p-3 space-y-1">
              <p className="text-xs font-semibold text-green-700 dark:text-green-400">Gói A — SEO</p>
              {titlesA.map((t, i) => (
                <p key={i} className="text-xs text-foreground/80 line-clamp-1">• {t}</p>
              ))}
            </div>
            <div className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-3 space-y-1">
              <p className="text-xs font-semibold text-amber-700 dark:text-amber-400">Gói B — Viral</p>
              {titlesB.map((t, i) => (
                <p key={i} className="text-xs text-foreground/80 line-clamp-1">• {t}</p>
              ))}
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => handleSeoApprove("a")}
              disabled={reviewSubmitting}
              className="flex-1 rounded-lg bg-green-600 px-3 py-2 text-xs font-semibold text-white hover:bg-green-700 disabled:opacity-40 transition-colors"
            >
              {reviewSubmitting ? <Loader2 className="h-3 w-3 animate-spin mx-auto" /> : "✅ Chọn Gói A"}
            </button>
            <button
              onClick={() => handleSeoApprove("b")}
              disabled={reviewSubmitting}
              className="flex-1 rounded-lg bg-amber-600 px-3 py-2 text-xs font-semibold text-white hover:bg-amber-700 disabled:opacity-40 transition-colors"
            >
              {reviewSubmitting ? <Loader2 className="h-3 w-3 animate-spin mx-auto" /> : "🔶 Chọn Gói B"}
            </button>
            <button
              onClick={handleSeoRedo}
              disabled={reviewSubmitting}
              className="rounded-lg border border-destructive px-3 py-2 text-xs font-medium text-destructive hover:bg-destructive/10 disabled:opacity-40 transition-colors"
            >
              Viết lại
            </button>
          </div>
        </div>
      )}

      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-xl font-bold">Gói SEO YouTube</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            AI tạo tiêu đề, mô tả, tags và thumbnail tối ưu CTR
          </p>
        </div>
        <button
          onClick={handleGenerate}
          disabled={loading}
          className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-xs font-medium hover:bg-muted transition-colors disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
          {seo ? "Tạo lại" : "Tạo SEO"}
        </button>
      </div>

      {/* Empty state */}
      {!seo && !loading && (
        <div className="flex flex-col items-center gap-4 rounded-xl border border-dashed border-border py-14 text-center">
          <Sparkles className="h-10 w-10 text-primary/40" />
          <div>
            <p className="font-medium text-sm">Chưa có gói SEO</p>
            <p className="text-xs text-muted-foreground mt-1">Nhấn "Tạo SEO" để AI tạo tiêu đề, mô tả, tags</p>
          </div>
          <button
            onClick={handleGenerate}
            className="flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90"
          >
            <Sparkles className="h-4 w-4" /> Tạo SEO ngay
          </button>
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center gap-3 rounded-xl border border-border bg-muted/30 py-10">
          <Loader2 className="h-5 w-5 animate-spin text-primary" />
          <span className="text-sm text-muted-foreground">Đang tạo gói SEO...</span>
        </div>
      )}

      {seo && (
        <>
          {/* Title selection */}
          <div className="space-y-2">
            <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
              Tiêu đề ({seo.title_variants.length} lựa chọn)
            </label>
            {seo.title_variants.map((title, idx) => (
              <button
                key={idx}
                onClick={() => setSelectedTitle(idx)}
                className={cn(
                  "flex w-full items-start gap-3 rounded-lg border p-3 text-left text-sm transition-all",
                  selectedTitle === idx
                    ? "border-primary bg-primary/5"
                    : "border-border hover:border-primary/30"
                )}
              >
                <div className={cn(
                  "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2 transition-colors",
                  selectedTitle === idx ? "border-primary bg-primary" : "border-border"
                )}>
                  {selectedTitle === idx && <Check className="h-2.5 w-2.5 text-white" />}
                </div>
                <span className="leading-snug">{title}</span>
                <span className={cn(
                  "ml-auto shrink-0 text-[10px] font-mono",
                  title.length > 70 ? "text-destructive" : "text-muted-foreground"
                )}>
                  {title.length}/70
                </span>
              </button>
            ))}
          </div>

          {/* Description */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Mô tả</label>
              <span className={cn("text-[10px] font-mono", charCount > 5000 ? "text-destructive" : "text-muted-foreground")}>
                {charCount.toLocaleString()}/5000
              </span>
            </div>
            <textarea
              value={description}
              onChange={e => setDescription(e.target.value)}
              rows={9}
              className="w-full rounded-lg border border-border bg-background px-4 py-3 text-sm leading-relaxed focus:outline-none focus:ring-2 focus:ring-primary/50 resize-y"
            />
          </div>

          {/* Tags */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Tags</label>
              <span className={cn("text-[10px] font-mono", tags.length > 500 ? "text-destructive" : "text-muted-foreground")}>
                {tags.length} tags
              </span>
            </div>
            <div className="flex flex-wrap gap-1.5 rounded-lg border border-border bg-background p-3 min-h-[80px]">
              {tags.map(tag => (
                <span
                  key={tag}
                  className="flex items-center gap-1 rounded-full border border-border bg-muted px-2.5 py-0.5 text-xs"
                >
                  #{tag}
                  <button onClick={() => removeTag(tag)} className="text-muted-foreground hover:text-destructive transition-colors">
                    <X className="h-2.5 w-2.5" />
                  </button>
                </span>
              ))}
              {/* Add tag input */}
              <div className="flex items-center gap-1">
                <input
                  value={newTag}
                  onChange={e => setNewTag(e.target.value)}
                  onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); addTag(); } }}
                  placeholder="Thêm tag..."
                  className="rounded-full border border-dashed border-border px-2.5 py-0.5 text-xs bg-transparent focus:outline-none focus:border-primary w-24"
                />
                <button onClick={addTag} className="text-muted-foreground hover:text-primary transition-colors">
                  <Plus className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          </div>

          {/* Thumbnail */}
          <div className="space-y-2">
            <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Thumbnail</label>
            <div className="flex gap-4 items-start">
              <div className="aspect-video w-44 overflow-hidden rounded-lg border border-border bg-muted flex items-center justify-center shrink-0">
                {seo.thumbnail_url ? (
                  <img src={seo.thumbnail_url} alt="thumbnail" className="h-full w-full object-cover rounded-lg" />
                ) : (
                  <ImageIcon className="h-8 w-8 text-muted-foreground/30" />
                )}
              </div>
              <div className="flex flex-col gap-2 pt-1">
                <button
                  onClick={handleGenerateThumbnail}
                  disabled={thumbLoading}
                  className="flex items-center gap-2 rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
                >
                  {thumbLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                  {seo.thumbnail_url ? "Tạo lại" : "Tạo thumbnail AI"}
                </button>
                <p className="text-[10px] text-muted-foreground leading-relaxed max-w-[180px]">
                  flux-1.1-ultra · 16:9 · Tự động tối ưu CTR
                </p>
              </div>
            </div>
          </div>

          {/* Save + Approve */}
          <div className="flex gap-3 pt-2">
            <button
              onClick={saveEdits}
              disabled={saving}
              className="flex items-center gap-2 rounded-lg border border-border px-4 py-2.5 text-sm font-medium hover:bg-muted transition-colors disabled:opacity-50"
            >
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              Lưu chỉnh sửa
            </button>
            <button
              onClick={() => setApproved(v => !v)}
              className={cn(
                "flex flex-1 items-center justify-center gap-2 rounded-lg py-2.5 text-sm font-semibold transition-all",
                approved
                  ? "bg-green-600 text-white hover:bg-green-700"
                  : "border border-border hover:bg-muted"
              )}
            >
              <Check className="h-4 w-4" />
              {approved ? "Đã duyệt gói SEO" : "Duyệt gói SEO"}
            </button>
          </div>
        </>
      )}

      <div className="flex justify-between pt-2">
        <button onClick={onBack} className="flex items-center gap-2 rounded-lg border border-border px-4 py-2.5 text-sm font-medium hover:bg-muted transition-colors">
          <ArrowLeft className="h-4 w-4" /> Quay lại
        </button>
        <button
          onClick={onNext}
          disabled={!canProceed}
          className="flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-40 transition-colors"
        >
          Đăng bài <ArrowRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
