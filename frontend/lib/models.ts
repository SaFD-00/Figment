// Model catalog + selection store (zustand).
// Holds the unified image + llm catalogs fetched from the backend and the user's
// current selection. Image/video models are selected PER MODE (txt2img/img2img/inpaint/
// edit/controlnet/reference/video); the LLM has a single selection. Persists in localStorage.

import { create } from "zustand";
import { listAllModels } from "./api";
import type { GenMode, Model } from "./types";

const GEN_MODES: GenMode[] = [
  "txt2img",
  "img2img",
  "inpaint",
  "edit",
  "controlnet",
  "reference",
  "video",
];

// Per-mode localStorage key, e.g. "figment.model.image.inpaint".
const lsImageKey = (mode: GenMode) => `figment.model.image.${mode}`;
const LS_LLM = "figment.model.llm";

function lsGet(key: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function lsSet(key: string, val: string) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, val);
  } catch {
    /* ignore */
  }
}

type ByMode = Record<GenMode, string | null>;

interface ModelsState {
  image: Model[];
  llm: Model[];
  loaded: boolean;
  loading: boolean;
  error: string | null;
  selectedByMode: ByMode;
  selectedLlmId: string | null;

  load: () => Promise<void>;
  setImageModel: (mode: GenMode, id: string) => void;
  setLlmModel: (id: string) => void;
  getImageModelForMode: (mode: GenMode) => string | null;
  selectedImageForMode: (mode: GenMode) => Model | null;
  selectedLlm: () => Model | null;
}

function pickDefault(models: Model[], preferred: string | null): string | null {
  if (preferred && models.some((m) => m.id === preferred)) return preferred;
  const ready = models.find((m) => m.ready);
  return (ready ?? models[0])?.id ?? null;
}

function emptyByMode(): ByMode {
  return {
    txt2img: null,
    img2img: null,
    inpaint: null,
    edit: null,
    controlnet: null,
    reference: null,
    video: null,
  };
}

// Build the per-mode selection from the catalog: restore each mode's localStorage
// pick (if still mode-compatible), else fall back to a sensible default for that mode.
function resolveByMode(image: Model[]): ByMode {
  const out = emptyByMode();
  for (const mode of GEN_MODES) {
    const compatible = image.filter((m) => m.modes.includes(mode));
    out[mode] = pickDefault(compatible, lsGet(lsImageKey(mode)));
  }
  return out;
}

export const useModelsStore = create<ModelsState>((set, get) => ({
  image: [],
  llm: [],
  loaded: false,
  loading: false,
  error: null,
  selectedByMode: emptyByMode(),
  selectedLlmId: null,

  load: async () => {
    if (get().loading || get().loaded) return;
    set({ loading: true, error: null });
    try {
      const cat = await listAllModels();
      set({
        image: cat.image,
        llm: cat.llm,
        loaded: true,
        loading: false,
        selectedByMode: resolveByMode(cat.image),
        selectedLlmId: pickDefault(cat.llm, lsGet(LS_LLM)),
      });
    } catch (e) {
      set({ loading: false, error: e instanceof Error ? e.message : String(e) });
    }
  },

  setImageModel: (mode, id) => {
    lsSet(lsImageKey(mode), id);
    set((s) => ({ selectedByMode: { ...s.selectedByMode, [mode]: id } }));
  },
  setLlmModel: (id) => {
    lsSet(LS_LLM, id);
    set({ selectedLlmId: id });
  },

  getImageModelForMode: (mode) => get().selectedByMode[mode],
  selectedImageForMode: (mode) => {
    const id = get().selectedByMode[mode];
    return get().image.find((m) => m.id === id) ?? null;
  },
  selectedLlm: () => get().llm.find((m) => m.id === get().selectedLlmId) ?? null,
}));
