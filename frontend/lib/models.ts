// Model catalog + selection store (zustand).
// Holds the unified image + llm catalogs fetched from the backend and the user's
// currently selected image / llm model. Persists selection in localStorage.

import { create } from "zustand";
import { listAllModels } from "./api";
import type { Model } from "./types";

const LS_IMAGE = "figment.model.image";
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

interface ModelsState {
  image: Model[];
  llm: Model[];
  loaded: boolean;
  loading: boolean;
  error: string | null;
  selectedImageId: string | null;
  selectedLlmId: string | null;

  load: () => Promise<void>;
  setImageModel: (id: string) => void;
  setLlmModel: (id: string) => void;
  selectedImage: () => Model | null;
  selectedLlm: () => Model | null;
}

function pickDefault(models: Model[], preferred: string | null): string | null {
  if (preferred && models.some((m) => m.id === preferred)) return preferred;
  const ready = models.find((m) => m.ready);
  return (ready ?? models[0])?.id ?? null;
}

export const useModelsStore = create<ModelsState>((set, get) => ({
  image: [],
  llm: [],
  loaded: false,
  loading: false,
  error: null,
  selectedImageId: null,
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
        selectedImageId: pickDefault(cat.image, lsGet(LS_IMAGE)),
        selectedLlmId: pickDefault(cat.llm, lsGet(LS_LLM)),
      });
    } catch (e) {
      set({ loading: false, error: e instanceof Error ? e.message : String(e) });
    }
  },

  setImageModel: (id) => {
    lsSet(LS_IMAGE, id);
    set({ selectedImageId: id });
  },
  setLlmModel: (id) => {
    lsSet(LS_LLM, id);
    set({ selectedLlmId: id });
  },

  selectedImage: () => get().image.find((m) => m.id === get().selectedImageId) ?? null,
  selectedLlm: () => get().llm.find((m) => m.id === get().selectedLlmId) ?? null,
}));
