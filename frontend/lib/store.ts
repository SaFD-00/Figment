// Global editor state (zustand).

import { create } from "zustand";
import type { Asset, GenSpec } from "./types";

export interface ActiveJob {
  id: string;
  progress: number; // 0..1
  node?: string;
  step?: number;
  total?: number;
  previewB64?: string;
  status: "queued" | "running" | "done" | "error";
  error?: string;
}

interface EditorState {
  currentProjectId: string | null;
  currentAsset: Asset | null;
  undoStack: Asset[];
  maskMode: boolean;
  brushSize: number;
  eraser: boolean;
  activeJob: ActiveJob | null;
  chatGenSpec: GenSpec | null;

  setCurrentProjectId: (id: string | null) => void;
  // Set current asset, optionally pushing the previous one onto the undo stack.
  setCurrentAsset: (asset: Asset | null, pushUndo?: boolean) => void;
  undo: () => void;
  canUndo: () => boolean;

  setMaskMode: (on: boolean) => void;
  setBrushSize: (n: number) => void;
  setEraser: (on: boolean) => void;

  setActiveJob: (job: ActiveJob | null) => void;
  updateActiveJob: (patch: Partial<ActiveJob>) => void;

  setChatGenSpec: (spec: GenSpec | null) => void;

  reset: () => void;
}

export const useEditorStore = create<EditorState>((set, get) => ({
  currentProjectId: null,
  currentAsset: null,
  undoStack: [],
  maskMode: false,
  brushSize: 40,
  eraser: false,
  activeJob: null,
  chatGenSpec: null,

  setCurrentProjectId: (id) => set({ currentProjectId: id }),

  setCurrentAsset: (asset, pushUndo = false) =>
    set((state) => {
      if (pushUndo && state.currentAsset) {
        return {
          currentAsset: asset,
          undoStack: [...state.undoStack, state.currentAsset],
        };
      }
      return { currentAsset: asset };
    }),

  undo: () =>
    set((state) => {
      if (state.undoStack.length === 0) return {};
      const prev = state.undoStack[state.undoStack.length - 1];
      return {
        currentAsset: prev,
        undoStack: state.undoStack.slice(0, -1),
      };
    }),

  canUndo: () => get().undoStack.length > 0,

  setMaskMode: (on) => set({ maskMode: on }),
  setBrushSize: (n) => set({ brushSize: n }),
  setEraser: (on) => set({ eraser: on }),

  setActiveJob: (job) => set({ activeJob: job }),
  updateActiveJob: (patch) =>
    set((state) =>
      state.activeJob
        ? { activeJob: { ...state.activeJob, ...patch } }
        : {},
    ),

  setChatGenSpec: (spec) => set({ chatGenSpec: spec }),

  reset: () =>
    set({
      currentAsset: null,
      undoStack: [],
      maskMode: false,
      eraser: false,
      activeJob: null,
      chatGenSpec: null,
    }),
}));
