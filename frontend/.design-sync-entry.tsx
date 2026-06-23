// design-sync preview harness — the bundle entry for claude.ai/design.
//
// Lives inside frontend/ (not repo-root .design-sync/) because the converter
// derives the package dir by walking up from --entry to the nearest named
// package.json — that must resolve to frontend/ (figment-frontend).
//
// Figment's frontend is a Next.js app, not a published component library, so
// there is no built dist/ entry. This file IS the converter's `--entry`: it
// re-exports exactly the components we sync (so they land on
// `window.Figment.*`) plus `DesignSyncProvider`, the wrapper configured as
// `cfg.provider`. The provider supplies the Next.js app-router context that
// `useRouter()`/`<Link>` need and seeds a mock model catalog + a mock backend
// fetch so data-driven cards (ModelPill, RecentProjects) render populated.
//
// IMPORTANT: this module has NO top-level side effects. All mocking lives
// inside DesignSyncProvider and only runs when it renders — which happens for
// PREVIEW CARDS ONLY (cfg.provider wraps them). A real design built with the
// DS imports the components but never renders DesignSyncProvider, so the
// mock fetch / seeded store never leak into anything the agent ships.

import "./.ds-process-shim"; // MUST be first — polyfills `process` before next/* init
import * as React from "react";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime";
import { useModelsStore } from "./lib/models";
import type { GenMode, Model, Project } from "./lib/types";

// ── components synced to claude.ai/design ────────────────────────────────
export { Button } from "./components/ui/Button";
export { Spinner } from "./components/ui/Spinner";
export { FeatureGrid } from "./components/home/FeatureGrid";
export { ProjectCard } from "./components/home/ProjectCard";
export { RecentProjects } from "./components/home/RecentProjects";
export { ModelPill, ModelPillRow } from "./components/models/ModelPicker";
export { PromptBox } from "./components/home/PromptBox";

// Re-exported so a preview .tsx can seed the SAME store instance the bundled
// components read (used by authored previews that need a specific selection).
export { useModelsStore } from "./lib/models";

// ── mock model catalog (realistic — mirrors Figment's local + cloud mix) ──
const IMAGE_MODELS: Model[] = [
  { id: "chroma-hd", label: "Chroma HD (local · quality txt2img)", family: "chroma", kind: "image", engine: "local-comfy", provider: null, vram_gb: 24, modes: ["txt2img", "img2img"], nsfw: false, uses_negative: true, cloud_model_id: null, vision: false, ready: true },
  { id: "flux-fill", label: "FLUX Fill (local · inpaint)", family: "flux", kind: "image", engine: "local-comfy", provider: null, vram_gb: 24, modes: ["inpaint", "edit"], nsfw: false, uses_negative: false, cloud_model_id: null, vision: false, ready: true },
  { id: "gemini-3.1-flash-image", label: "Gemini 3.1 Flash Image (cloud)", family: "gemini", kind: "image", engine: "cloud-openrouter", provider: "google", vram_gb: 0, modes: ["txt2img", "img2img", "edit", "reference"], nsfw: false, uses_negative: false, cloud_model_id: "google/gemini-3.1-flash-image", vision: true, ready: true },
  { id: "gpt-5.4-image-2", label: "GPT-5.4 Image (cloud)", family: "gpt", kind: "image", engine: "cloud-openrouter", provider: "openai", vram_gb: 0, modes: ["txt2img", "edit"], nsfw: false, uses_negative: false, cloud_model_id: "openai/gpt-5.4-image-2", vision: false, ready: true },
];

const LLM_MODELS: Model[] = [
  { id: "qwen3-vl-local", label: "Qwen3-VL 8B (local · vision)", family: "qwen", kind: "llm", engine: "local-ollama", provider: null, vram_gb: 8, modes: [], nsfw: false, uses_negative: false, cloud_model_id: null, vision: true, ready: true },
  { id: "gpt-5.4", label: "GPT-5.4 (cloud · vision)", family: "gpt", kind: "llm", engine: "cloud-openrouter", provider: "openai", vram_gb: 0, modes: [], nsfw: false, uses_negative: false, cloud_model_id: "openai/gpt-5.4", vision: true, ready: true },
];

const GEN_MODES: GenMode[] = ["txt2img", "img2img", "inpaint", "edit", "controlnet", "reference", "video", "figure"];

// ── mock projects (so RecentProjects shows a real grid, not the empty state) ─
const MOCK_PROJECTS: Project[] = [
  { id: "p-aurora", title: "Aurora reaction pathway", cover_asset: undefined, created_at: "2026-06-20T09:12:00Z", updated_at: "2026-06-22T14:30:00Z" },
  { id: "p-cells", title: "Cell signalling overview", cover_asset: undefined, created_at: "2026-06-18T11:00:00Z", updated_at: "2026-06-21T08:05:00Z" },
  { id: "p-flow", title: "Data pipeline diagram", cover_asset: undefined, created_at: "2026-06-15T16:40:00Z", updated_at: "2026-06-19T19:20:00Z" },
  { id: "p-orbit", title: "Orbital mechanics sketch", cover_asset: undefined, created_at: "2026-06-10T07:25:00Z", updated_at: "2026-06-17T10:10:00Z" },
];

const mockRouter = {
  push: () => {},
  replace: () => {},
  refresh: () => {},
  back: () => {},
  forward: () => {},
  prefetch: () => Promise.resolve(),
} as const;

// Seed once, lazily — only when a preview actually renders DesignSyncProvider.
let primed = false;
function primePreviewEnv(): void {
  if (primed) return;
  primed = true;

  useModelsStore.setState({
    image: IMAGE_MODELS,
    llm: LLM_MODELS,
    loaded: true, // makes store.load() a no-op so no real /models fetch fires
    loading: false,
    error: null,
    selectedByMode: Object.fromEntries(
      GEN_MODES.map((m) => [m, IMAGE_MODELS.find((x) => x.modes.includes(m))?.id ?? IMAGE_MODELS[0].id]),
    ) as Record<GenMode, string | null>,
    selectedLlmId: "qwen3-vl-local",
  });

  if (typeof window !== "undefined" && !(window as unknown as { __dsFetchPatched?: boolean }).__dsFetchPatched) {
    const orig = window.fetch.bind(window);
    const json = (data: unknown) =>
      Promise.resolve(new Response(JSON.stringify(data), { status: 200, headers: { "Content-Type": "application/json" } }));
    window.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : (input as Request).url;
      const method = (init?.method ?? "GET").toUpperCase();
      if (url.includes("/api/projects") && method === "GET") return json(MOCK_PROJECTS);
      if (url.includes("/api/models/all")) return json({ image: IMAGE_MODELS, llm: LLM_MODELS });
      if (url.includes("/api/models")) return json(IMAGE_MODELS);
      return orig(input as RequestInfo, init);
    }) as typeof window.fetch;
    (window as unknown as { __dsFetchPatched?: boolean }).__dsFetchPatched = true;
  }
}

/**
 * Preview wrapper (cfg.provider). Supplies the Next.js app-router context and
 * primes the mock model store + backend fetch so data-driven components render
 * populated. Only rendered for preview cards, never in shipped designs.
 */
export function DesignSyncProvider({ children }: { children?: React.ReactNode }) {
  primePreviewEnv();
  return React.createElement(AppRouterContext.Provider, { value: mockRouter as never }, children);
}
