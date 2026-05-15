"use client";

import { useEffect, useRef } from "react";
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
  // 3 interrupt checkpoints
  if (paused_at === "seo_review") return 7;                 // Trạm 3 — StepSEO
  if (paused_at === "shot_review") return 4;                // Trạm 2 — StepSceneBreakdown
  if (paused_at === "character_review") return 3;           // Trạm 1 — StepCharacter
  // Running stages
  if (current_stage === "seo_agent" || current_stage === "seo_review") return 7;
  if (
    current_stage === "video_editor" || current_stage === "video_validator" ||
    current_stage === "final_assembler" || current_stage === "continuity_director" ||
    current_stage === "shot_review"
  ) return 5;                                               // StepGeneration
  if (
    current_stage === "cinematic_decomposer" ||
    current_stage === "scene_planner" ||
    current_stage === "scene_review"
  ) return 4;                                               // StepSceneBreakdown
  if (current_stage === "character_designer" || current_stage === "character_scorer") return 3;
  if (current_stage === "screenwriter" || current_stage === "script_scorer") return 2;
  if (status === "completed") return 7;
  return 0;
}

export default function ShortVideoWizard() {
  const { stepIndex, nextStep, prevStep, project, setProject, reset, setStepIndex } = useWizardStore();

  // On mount: jump to correct step based on pipeline state
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

  // Poll pipeline state every 5s when at an interrupt step (Trạm 1/2/3).
  // Detects when email approval was done → auto-advances wizard without requiring
  // a second click on the dashboard.
  const INTERRUPT_STEPS = new Set([3, 4, 7]);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => {
    if (!project?.id || !INTERRUPT_STEPS.has(stepIndex)) {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
      return;
    }
    pollRef.current = setInterval(() => {
      fetch(`${BASE}/pipeline/${project.id}/state`)
        .then((r) => r.json())
        .then((state) => {
          const target = pipelineStateToStep(state);
          if (target !== stepIndex) setStepIndex(Math.max(target, stepIndex));
        })
        .catch(() => {});
    }, 5000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [project?.id, stepIndex]);

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
