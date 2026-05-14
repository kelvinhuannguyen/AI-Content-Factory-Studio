"use client";

import { WizardShell } from "@/components/layout/WizardShell";
import { SHORT_VIDEO_STEPS } from "@/lib/constants";
import StepTopic from "./_steps/StepTopic";
import StepScript from "./_steps/StepScript";
import StepConfig from "./_steps/StepConfig";
import StepCharacter from "./_steps/StepCharacter";
import StepSceneBreakdown from "./_steps/StepSceneBreakdown";
import StepGeneration from "./_steps/StepGeneration";
import StepQualityReview from "./_steps/StepQualityReview";
import StepSEO from "./_steps/StepSEO";
import StepPublish from "./_steps/StepPublish";
import { useWizardStore } from "@/stores/wizardStore";

const STEP_COMPONENTS = [
  StepTopic, StepConfig, StepScript, StepCharacter,
  StepSceneBreakdown, StepGeneration, StepQualityReview,
  StepSEO, StepPublish,
];

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export default function ShortVideoWizard() {
  const { stepIndex, nextStep, prevStep, project, setProject, reset } = useWizardStore();

  const currentStep = SHORT_VIDEO_STEPS[stepIndex] ?? SHORT_VIDEO_STEPS[0];
  const StepComponent = STEP_COMPONENTS[stepIndex] ?? StepTopic;

  const stepProps = {
    projectId: project?.id ?? null,
    onProjectCreated: (id: string) =>
      setProject({ id, title: "Dự án mới", production_type: "short_video", status: "draft", preferred_language: "vi" }),
    onNext: nextStep,
    onBack: prevStep,
    isFirst: stepIndex === 0,
    isLast: stepIndex === SHORT_VIDEO_STEPS.length - 1,
  };

  async function handleReset() {
    if (project?.id) {
      await fetch(`${BASE}/pipeline/${project.id}/reset`, { method: "DELETE" }).catch(() => {});
    }
    reset();
  }

  return (
    <WizardShell
      steps={SHORT_VIDEO_STEPS}
      currentStepId={currentStep.id}
      title="Video ngắn"
      onReset={handleReset}
    >
      <StepComponent {...stepProps} />
    </WizardShell>
  );
}
