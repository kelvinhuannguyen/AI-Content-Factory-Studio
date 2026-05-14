"use client";

import { useEffect } from "react";
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

function pipelineStateToStep(state: { paused_at?: string; current_stage?: string; status?: string }): number {
  const { paused_at, current_stage, status } = state;
  if (paused_at === "video_review") return 6;
  if (paused_at === "scene_review") return 4;
  if (paused_at === "character_review") return 3;
  if (paused_at === "script_review") return 2;
  if (current_stage === "video_editor" || current_stage === "video_validator") return 5;
  if (current_stage === "scene_planner" || current_stage === "scene_review") return 4;
  if (current_stage === "character_designer") return 3;
  if (current_stage === "screenwriter" || current_stage === "script_scorer") return 2;
  if (status === "completed") return 6;
  return 0;
}

export default function ShortVideoWizard() {
  const { stepIndex, nextStep, prevStep, project, setProject, reset, setStepIndex } = useWizardStore();

  // On mount with an existing project, jump to the correct wizard step based on pipeline state
  useEffect(() => {
    if (!project?.id) return;
    fetch(`${BASE}/pipeline/${project.id}/state`)
      .then((r) => r.json())
      .then((state) => {
        const target = pipelineStateToStep(state);
        if (target > stepIndex) setStepIndex(target);
      })
      .catch(() => {});
  }, [project?.id]);

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
