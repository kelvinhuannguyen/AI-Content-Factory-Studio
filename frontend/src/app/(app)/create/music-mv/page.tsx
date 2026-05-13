"use client";

import { WizardShell } from "@/components/layout/WizardShell";
import { MUSIC_MV_STEPS } from "@/lib/constants";
import { useState } from "react";

export default function MusicMVWizard() {
  const [stepIndex, setStepIndex] = useState(0);
  const currentStep = MUSIC_MV_STEPS[stepIndex];

  return (
    <WizardShell steps={MUSIC_MV_STEPS} currentStepId={currentStep.id} title="MV ca nhạc">
      <div className="flex flex-col items-center justify-center gap-4 rounded-xl border border-dashed border-border py-24 text-center">
        <p className="text-lg font-semibold">Bước: {currentStep.label}</p>
        <p className="text-sm text-muted-foreground">Phase 2 — MV với Suno AI</p>
      </div>
    </WizardShell>
  );
}
