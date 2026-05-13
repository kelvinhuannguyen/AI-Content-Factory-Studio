import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { ProductionType, ProjectStatus } from "@/types/project";

export interface WizardProject {
  id: string;
  title: string;
  production_type: ProductionType;
  status: ProjectStatus;
  preferred_language: string;
}

export interface WizardState {
  // Active project
  project: WizardProject | null;
  stepIndex: number;

  // Step data cache (avoids re-fetching on back navigation)
  topic: string | null;
  scriptId: string | null;
  scriptApproved: boolean;
  durationSeconds: number | null;
  genre: string | null;
  style: string | null;
  aspectRatio: string | null;
  characterId: string | null;
  characterDescription: string | null;
  characterName: string | null;
  musicTrackId: string | null;
  pipelineStarted: boolean;

  // Actions
  setProject: (p: WizardProject) => void;
  setStepIndex: (i: number) => void;
  nextStep: () => void;
  prevStep: () => void;
  setTopic: (t: string) => void;
  setScriptId: (id: string, approved?: boolean) => void;
  setScriptApproved: (v: boolean) => void;
  setConfig: (d: number, g: string, s: string, ar: string) => void;
  setCharacterId: (id: string) => void;
  setCharacterConfig: (description: string, name: string) => void;
  setMusicTrackId: (id: string) => void;
  setPipelineStarted: (v: boolean) => void;
  reset: () => void;
}

const INITIAL: Omit<WizardState, keyof { setProject: unknown; setStepIndex: unknown; nextStep: unknown; prevStep: unknown; setTopic: unknown; setScriptId: unknown; setScriptApproved: unknown; setConfig: unknown; setCharacterId: unknown; setCharacterConfig: unknown; setMusicTrackId: unknown; setPipelineStarted: unknown; reset: unknown }> = {
  project: null,
  stepIndex: 0,
  topic: null,
  scriptId: null,
  scriptApproved: false,
  durationSeconds: null,
  genre: null,
  style: null,
  aspectRatio: null,
  characterId: null,
  characterDescription: null,
  characterName: null,
  musicTrackId: null,
  pipelineStarted: false,
};

export const useWizardStore = create<WizardState>()(
  persist(
    (set, get) => ({
      ...INITIAL,

      setProject: (p) => set({ project: p, stepIndex: 0 }),
      setStepIndex: (i) => set({ stepIndex: i }),
      nextStep: () => set({ stepIndex: get().stepIndex + 1 }),
      prevStep: () => set({ stepIndex: Math.max(0, get().stepIndex - 1) }),
      setTopic: (t) => set({ topic: t }),
      setScriptId: (id, approved = false) => set({ scriptId: id, scriptApproved: approved }),
      setScriptApproved: (v) => set({ scriptApproved: v }),
      setConfig: (d, g, s, ar) => set({ durationSeconds: d, genre: g, style: s, aspectRatio: ar }),
      setCharacterId: (id) => set({ characterId: id }),
      setCharacterConfig: (description, name) => set({ characterDescription: description, characterName: name }),
      setMusicTrackId: (id) => set({ musicTrackId: id }),
      setPipelineStarted: (v) => set({ pipelineStarted: v }),
      reset: () => set(INITIAL as WizardState),
    }),
    {
      name: "aicfs-wizard",
      partialize: (s) => ({
        project: s.project,
        stepIndex: s.stepIndex,
        topic: s.topic,
        scriptId: s.scriptId,
        scriptApproved: s.scriptApproved,
        durationSeconds: s.durationSeconds,
        genre: s.genre,
        style: s.style,
        aspectRatio: s.aspectRatio,
        characterId: s.characterId,
        characterDescription: s.characterDescription,
        characterName: s.characterName,
        musicTrackId: s.musicTrackId,
        pipelineStarted: s.pipelineStarted,
      }),
    }
  )
);
