export interface StepProps {
  projectId: string | null;
  onProjectCreated: (id: string) => void;
  onNext: () => void;
  onBack: () => void;
  isFirst: boolean;
  isLast: boolean;
}
