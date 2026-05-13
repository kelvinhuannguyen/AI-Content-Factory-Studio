import { useWizardStore } from "@/stores/wizardStore";
import type { Step } from "@/lib/constants";

export function useWizard(steps: readonly { id: string; label: string }[]) {
  const { stepIndex, nextStep, prevStep, setStepIndex } = useWizardStore();

  const currentStep = steps[stepIndex] ?? steps[0];
  const isFirst = stepIndex === 0;
  const isLast = stepIndex === steps.length - 1;

  return {
    stepIndex,
    currentStep,
    isFirst,
    isLast,
    next: nextStep,
    back: prevStep,
    goTo: setStepIndex,
  };
}
