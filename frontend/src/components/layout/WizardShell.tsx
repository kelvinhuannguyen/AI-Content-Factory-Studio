"use client";

import { cn } from "@/lib/utils";
import { Check } from "lucide-react";

interface Step {
  id: string;
  label: string;
}

interface WizardShellProps {
  steps: Step[];
  currentStepId: string;
  children: React.ReactNode;
  title?: string;
}

export function WizardShell({ steps, currentStepId, children, title }: WizardShellProps) {
  const currentIndex = steps.findIndex((s) => s.id === currentStepId);

  return (
    <div className="flex min-h-screen bg-background">
      {/* Step sidebar */}
      <aside className="w-56 shrink-0 border-r border-border bg-[hsl(var(--sidebar-bg))] p-6">
        {title && (
          <p className="mb-6 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {title}
          </p>
        )}
        <ol className="space-y-1">
          {steps.map((step, idx) => {
            const isDone = idx < currentIndex;
            const isCurrent = idx === currentIndex;
            return (
              <li key={step.id} className="flex items-center gap-3">
                <div
                  className={cn(
                    "flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold",
                    isDone
                      ? "bg-primary text-primary-foreground"
                      : isCurrent
                      ? "border-2 border-primary text-primary"
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
      </aside>

      {/* Step content */}
      <div className="flex-1 overflow-y-auto p-8">{children}</div>
    </div>
  );
}
