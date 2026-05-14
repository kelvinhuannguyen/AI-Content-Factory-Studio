"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { CheckCircle2, Clock, AlertCircle, ArrowLeft, ArrowRight, Loader2, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { useSSE } from "@/hooks/useSSE";
import { useWizardStore } from "@/stores/wizardStore";
import type { StepProps } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

type TaskStatus = "waiting" | "running" | "done" | "failed";

interface Task {
  id: string;
  label: string;
  task_type: string;
  status: TaskStatus;
  item_id?: string;  // Shot.id or Scene.id — matches SSE event scene_id
}

const STATUS_ICON: Record<TaskStatus, React.ReactNode> = {
  waiting:  <Clock className="h-4 w-4 text-muted-foreground" />,
  running:  <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />,
  done:     <CheckCircle2 className="h-4 w-4 text-green-500" />,
  failed:   <AlertCircle className="h-4 w-4 text-destructive" />,
};

export default function StepGeneration({ onNext, onBack }: StepProps) {
  const { project } = useWizardStore();
  const projectId = project?.id ?? null;

  const [tasks, setTasks] = useState<Task[]>([]);
  const [pipelineMsg, setPipelineMsg] = useState("");
  const [retrying, setRetrying] = useState(false);
  const [stuckTimer, setStuckTimer] = useState(false);
  const stuckRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Load shots first (cinematic mode), fall back to scenes
  useEffect(() => {
    if (!projectId) return;

    const buildFromShots = async () => {
      try {
        const r = await fetch(`${BASE}/shots/${projectId}`);
        const shots = await r.json();
        if (Array.isArray(shots) && shots.length > 0) {
          const initialTasks: Task[] = [
            ...shots.map((s: { id: string; shot_id: string; shot_number: number }) => ({
              id: `clip_${s.id}`,
              label: `Shot ${s.shot_id || s.shot_number}`,
              task_type: "video_clip",
              status: "waiting" as TaskStatus,
              item_id: s.id,
            })),
            { id: "tts", label: "Giọng đọc (TTS)", task_type: "voiceover", status: "waiting" },
            { id: "assembly", label: "Dựng video (FFmpeg)", task_type: "assembly", status: "waiting" },
          ];
          setTasks(initialTasks);
          return;
        }
      } catch {/* fall through */}

      // Fallback: build from scenes
      try {
        const r = await fetch(`${BASE}/scenes/${projectId}`);
        const scenes = await r.json();
        if (Array.isArray(scenes) && scenes.length > 0) {
          const initialTasks: Task[] = [
            ...scenes.map((s: { id: string; scene_number: number; title: string }) => ({
              id: `clip_${s.id}`,
              label: `Video clip — Cảnh ${s.scene_number}: ${s.title}`,
              task_type: "video_clip",
              status: "waiting" as TaskStatus,
              item_id: s.id,
            })),
            { id: "tts", label: "Giọng đọc (TTS)", task_type: "voiceover", status: "waiting" },
            { id: "assembly", label: "Dựng video (FFmpeg)", task_type: "assembly", status: "waiting" },
          ];
          setTasks(initialTasks);
          return;
        }
      } catch {/* fall through */}

      setTasks([
        { id: "clip1", label: "Video clips", task_type: "video_clip", status: "waiting" },
        { id: "tts", label: "Giọng đọc", task_type: "voiceover", status: "waiting" },
        { id: "assembly", label: "Dựng video (FFmpeg)", task_type: "assembly", status: "waiting" },
      ]);
    };

    buildFromShots();
  }, [projectId]);

  // Stuck detection: if tasks loaded but none progressed after 90s, show retry
  useEffect(() => {
    if (tasks.length === 0) return;
    const allWaiting = tasks.every((t) => t.status === "waiting");
    if (allWaiting) {
      stuckRef.current = setTimeout(() => setStuckTimer(true), 90_000);
    } else {
      setStuckTimer(false);
      if (stuckRef.current) clearTimeout(stuckRef.current);
    }
    return () => { if (stuckRef.current) clearTimeout(stuckRef.current); };
  }, [tasks]);

  const handleRetry = async () => {
    if (!projectId || retrying) return;
    setRetrying(true);
    setStuckTimer(false);
    try {
      await fetch(`${BASE}/pipeline/${projectId}/continue`, { method: "POST" });
      setPipelineMsg("Đã gửi lệnh retry — pipeline đang khởi động lại...");
    } catch {
      setPipelineMsg("Retry thất bại — kiểm tra kết nối mạng.");
    } finally {
      setTimeout(() => setRetrying(false), 3000);
    }
  };

  // SSE event handler
  const handleSSE = useCallback((event: { type: string; task_type?: string; scene_id?: string; message?: string; error?: string }) => {
    const { type, task_type, scene_id } = event;

    if (type === "agent_start" && (event as any).agent === "cinematic_decomposer") {
      setPipelineMsg(event.message || "Cinematic Director đang phân rã cảnh quay thành shots ≤8s...");
    } else if (type === "agent_done" && (event as any).agent === "cinematic_decomposer") {
      const shotCount = (event as any).shot_count ?? 0;
      setPipelineMsg(`Phân rã hoàn thành — ${shotCount} shots sẵn sàng để phân tích continuity`);
    } else if (type === "agent_start" && (event as any).agent === "continuity_director") {
      setPipelineMsg(event.message || "Continuity Director đang tạo Master Render List...");
    } else if (type === "agent_done" && (event as any).agent === "continuity_director") {
      const motionAvg = (event as any).motion_intensity_avg;
      setPipelineMsg(
        motionAvg != null
          ? `Master Render List sẵn sàng — avg intensity ${motionAvg} · Bắt đầu render video...`
          : "Continuity Director hoàn thành · Bắt đầu render video..."
      );
    } else if (type === "agent_done" && (event as any).agent === "video_editor") {
      setPipelineMsg(event.message || "Clips & audio sẵn sàng — chuyển sang Final Assembler...");
    } else if (type === "agent_start" && (event as any).agent === "final_assembler") {
      setPipelineMsg(event.message || "Final Assembler đang dựng & hoàn thiện video...");
    } else if (type === "agent_done" && (event as any).agent === "final_assembler") {
      const cc = (event as any).clip_count ?? 0;
      const hasSfx = (event as any).has_sfx;
      setPipelineMsg(
        `Video hoàn chỉnh — ${cc} clips · xfade · color grade${hasSfx ? " · SFX ambient" : ""} · Đang chấm điểm...`
      );
    } else if (type === "pipeline_start" || type === "pipeline_queued") {
      setPipelineMsg(event.message || "Pipeline đang render video...");
    } else if (type === "task_start" && task_type) {
      setTasks((prev) => prev.map((t) => {
        const matches = task_type === t.task_type && (!scene_id || t.item_id === scene_id);
        return matches ? { ...t, status: "running" } : t;
      }));
    } else if (type === "task_done" && task_type) {
      setTasks((prev) => prev.map((t) => {
        const matches = task_type === t.task_type && (!scene_id || t.item_id === scene_id);
        return matches ? { ...t, status: "done" } : t;
      }));
    } else if (type === "task_error" && task_type) {
      setTasks((prev) => prev.map((t) => {
        const matches = task_type === t.task_type && (!scene_id || t.item_id === scene_id);
        return matches ? { ...t, status: "failed" } : t;
      }));
    }
  }, []);

  useSSE(projectId, handleSSE);

  const doneCount = tasks.filter((t) => t.status === "done").length;
  const totalProgress = tasks.length > 0 ? Math.round((doneCount / tasks.length) * 100) : 0;
  const allDone = tasks.length > 0 && doneCount === tasks.length;
  const hasError = tasks.some((t) => t.status === "failed");

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h2 className="text-xl font-bold">Tạo media</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Kling-3-Pro + TTS + FFmpeg · tiến độ cập nhật realtime qua SSE
        </p>
      </div>

      {tasks.length === 0 ? (
        <div className="flex items-center gap-3 rounded-xl border border-primary/20 bg-primary/5 p-4">
          <Loader2 className="h-5 w-5 animate-spin text-primary shrink-0" />
          <div>
            <p className="text-sm font-medium text-primary">Pipeline đang tạo media...</p>
            <p className="text-xs text-muted-foreground mt-0.5">Kling-3-Pro + TTS + FFmpeg · Tải danh sách tác vụ...</p>
          </div>
        </div>
      ) : (
        <>
          {pipelineMsg && (
            <div className="rounded-lg border border-primary/20 bg-primary/5 px-4 py-3 text-sm text-primary">
              {pipelineMsg}
            </div>
          )}

          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span className="font-medium">Tiến độ tổng</span>
              <span className="text-muted-foreground">{doneCount}/{tasks.length} tác vụ · {totalProgress}%</span>
            </div>
            <div className="h-2.5 w-full overflow-hidden rounded-full bg-muted">
              <div
                className={cn(
                  "h-full rounded-full transition-all duration-700",
                  hasError ? "bg-destructive" : "bg-primary"
                )}
                style={{ width: `${totalProgress}%` }}
              />
            </div>
          </div>

          <div className="space-y-2">
            {tasks.map((task) => (
              <div
                key={task.id}
                className={cn(
                  "flex items-center gap-3 rounded-lg border p-3 transition-all",
                  task.status === "done"    ? "border-green-500/30 bg-green-500/5" :
                  task.status === "running" ? "border-primary/30 bg-primary/5 animate-pulse" :
                  task.status === "failed"  ? "border-destructive/30 bg-destructive/5" :
                  "border-border bg-card opacity-60"
                )}
              >
                {STATUS_ICON[task.status]}
                <span className="flex-1 text-sm">{task.label}</span>
                <span className={cn(
                  "text-xs",
                  task.status === "done"    ? "text-green-600" :
                  task.status === "running" ? "text-primary" :
                  task.status === "failed"  ? "text-destructive" :
                  "text-muted-foreground"
                )}>
                  {task.status === "done"    ? "Xong" :
                   task.status === "running" ? "Đang xử lý..." :
                   task.status === "failed"  ? "Lỗi" :
                   "Chờ..."}
                </span>
              </div>
            ))}
          </div>

          {/* Stuck banner: no progress after 90s */}
          {stuckTimer && !allDone && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4">
              <p className="text-sm font-medium text-amber-700 dark:text-amber-400">
                Có vẻ pipeline bị dừng (server restart?)
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Server có thể đã khởi động lại giữa chừng. Nhấn Retry để tiếp tục từ điểm đã dừng.
              </p>
              <button
                onClick={handleRetry}
                disabled={retrying}
                className="mt-3 flex items-center gap-2 rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-600 disabled:opacity-60 transition-colors"
              >
                {retrying ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                {retrying ? "Đang retry..." : "Retry pipeline"}
              </button>
            </div>
          )}

          {allDone && (
            <div className="rounded-lg border border-green-500/30 bg-green-500/10 p-4 text-center">
              <p className="font-semibold text-green-700 dark:text-green-400">Tất cả tác vụ hoàn thành!</p>
              <p className="mt-1 text-sm text-muted-foreground">Video đã sẵn sàng để chấm điểm chất lượng</p>
            </div>
          )}

          {hasError && !allDone && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-center">
              <p className="font-semibold text-destructive text-sm">Một số tác vụ thất bại</p>
              <p className="mt-1 text-xs text-muted-foreground">Kiểm tra Railway logs để biết chi tiết</p>
            </div>
          )}
        </>
      )}

      <div className="flex justify-between pt-2">
        <button onClick={onBack} className="flex items-center gap-2 rounded-lg border border-border px-4 py-2.5 text-sm font-medium hover:bg-muted transition-colors">
          <ArrowLeft className="h-4 w-4" /> Quay lại
        </button>
        <button
          onClick={onNext}
          disabled={!allDone}
          className="flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-40 transition-colors"
        >
          Xem kết quả <ArrowRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
