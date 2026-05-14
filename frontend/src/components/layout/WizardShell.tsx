"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { Check, RotateCcw, Loader2 } from "lucide-react";

interface Step {
  id: string;
  label: string;
}

interface WizardShellProps {
  steps: Step[];
  currentStepId: string;
  children: React.ReactNode;
  title?: string;
  onReset?: () => Promise<void>;
}

export function WizardShell({ steps, currentStepId, children, title, onReset }: WizardShellProps) {
  const currentIndex = steps.findIndex((s) => s.id === currentStepId);
  const [resetting, setResetting] = useState(false);
  const [confirm, setConfirm] = useState(false);

  async function handleReset() {
    if (!confirm) { setConfirm(true); return; }
    setResetting(true);
    try { await onReset?.(); } finally { setResetting(false); setConfirm(false); }
  }

  return (
    <div className="flex min-h-screen bg-background">
      {/* Step sidebar */}
      <aside className="w-56 shrink-0 border-r border-border bg-[hsl(var(--sidebar-bg))] flex flex-col p-6">
        {title && (
          <p className="mb-6 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {title}
          </p>
        )}
        <ol className="space-y-1 flex-1">
          {steps.map((step, idx) => {
            const isDone = idx < currentIndex;
            const isCurrent = idx === currentIndex;
            return (
              <li key={step.id} className="flex items-center gap-3">
                <div
                  className={cn(
                    "flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold transition-all duration-300",
                    isDone
                      ? "bg-primary text-primary-foreground shadow-[0_0_10px_hsl(var(--primary)/0.4)]"
                      : isCurrent
                      ? "border-2 border-primary bg-primary/15 text-primary font-bold"
                      : "border border-border text-muted-foreground"
                  )}
                >
                  {isDone ? <Check className="h-3.5 w-3.5" /> : idx + 1}
                </div>
                <span
                  className={cn(
                    "text-sm",
                    isCurrent ? "font-semibold text-foreground" : isDone ? "text-foreground" : "text-muted-foreground"
                  )}
                >
                  {step.label}
                </span>
              </li>
            );
          })}
        </ol>

        {/* Reset button — only show if onReset provided and past step 0 */}
        {onReset && currentIndex > 0 && (
          <div className="mt-6 border-t border-border pt-4">
            <button
              onClick={handleReset}
              disabled={resetting}
              onBlur={() => setConfirm(false)}
              className={cn(
                "flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs font-medium transition-all",
                confirm
                  ? "bg-destructive text-white hover:bg-destructive/90"
                  : "border border-border text-muted-foreground hover:border-destructive/50 hover:text-destructive"
              )}
            >
              {resetting
                ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                : <RotateCcw className="h-3.5 w-3.5" />}
              {resetting ? "Đang reset..." : confirm ? "Xác nhận?" : "Bắt đầu lại"}
            </button>
            {confirm && (
              <p className="mt-1.5 text-center text-[10px] text-muted-foreground">
                Click lần nữa để xác nhận
              </p>
            )}
          </div>
        )}
      </aside>

      {/* Step content */}
      <div className="flex-1 overflow-y-auto p-8">{children}</div>
    </div>
  );
}
