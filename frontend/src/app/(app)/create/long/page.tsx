"use client";

import { WizardShell } from "@/components/layout/WizardShell";
import { LONG_VIDEO_STEPS } from "@/lib/constants";
import { useState } from "react";

export default function LongVideoWizard() {
  const [stepIndex, setStepIndex] = useState(0);
  const currentStep = LONG_VIDEO_STEPS[stepIndex];

  return (
    <WizardShell steps={LONG_VIDEO_STEPS} currentStepId={currentStep.id} title="Video dài">
      <div className="flex flex-col items-center justify-center gap-4 rounded-xl border border-dashed border-border py-24 text-center">
        <p className="text-lg font-semibold">Bước: {currentStep.label}</p>
        <p className="text-sm text-muted-foreground">Sprint 2 — Video dài (tương tự video ngắn)</p>
      </div>
    </WizardShell>
  );
}
