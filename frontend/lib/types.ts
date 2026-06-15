// Shared TypeScript types mirroring the backend API contract.

export type AssetKind =
  | "source"
  | "reference"
  | "mask"
  | "output"
  | "upscaled"
  | "nobg"
  | string;

export interface Asset {
  id: string;
  project_id: string;
  kind: AssetKind;
  path: string;
  width?: number;
  height?: number;
  parent_id?: string;
  meta: Record<string, unknown>;
  created_at: string;
}

export interface Project {
  id: string;
  title: string;
  cover_asset?: string;
  created_at: string;
  updated_at: string;
}

export type ChatRole = "user" | "assistant";

export interface ChatMessage {
  id: string;
  project_id: string;
  role: ChatRole;
  content: string;
  genspec?: GenSpec;
  // Optional: an assistant turn that produced an image may carry the resulting
  // asset id so the UI can render a thumbnail inline.
  result_asset?: string;
  created_at: string;
}

export type JobStatus = "queued" | "running" | "done" | "error" | "canceled";

export interface Job {
  id: string;
  project_id: string;
  mode: GenMode;
  status: JobStatus;
  progress: number;
  result_asset?: string;
  error?: string;
  created_at: string;
  updated_at: string;
}

export type GenMode =
  | "txt2img"
  | "img2img"
  | "inpaint"
  | "edit"
  | "controlnet"
  | "reference";

export type ReferenceRole = "style" | "structure" | "edit" | "identity";

export interface ReferenceImage {
  asset: string;
  role: ReferenceRole;
  strength: number;
}

export type ControlNetType = "canny" | "depth" | "scribble" | "lineart";

export interface Lora {
  name: string;
  weight: number;
}

export interface GenSpec {
  version: 1;
  mode: GenMode;
  model: string | null;
  llm_model: string | null;
  prompt: string;
  negative_prompt: string;
  width: number;
  height: number;
  steps: number | null;
  cfg: number | null;
  sampler: string | null;
  scheduler: string | null;
  seed: number | null;
  batch: number;
  denoise: number;
  source_asset: string | null;
  mask_asset: string | null;
  reference_images: ReferenceImage[];
  controlnet_type: ControlNetType | null;
  controlnet_strength: number;
  loras: Lora[];
  upscale: boolean;
  remove_bg: boolean;
}

export type ModelKind = "image" | "llm";
export type ModelEngine =
  | "local-comfy"
  | "local-ollama"
  | "cloud-openrouter"
  | "cloud-openai";

export interface Model {
  id: string;
  label: string;
  family: string;
  kind: ModelKind;
  engine: ModelEngine;
  provider: string | null;
  vram_gb: number;
  modes: string[];
  nsfw: boolean;
  uses_negative: boolean;
  cloud_model_id: string | null;
  ready: boolean;
}

export interface ModelCatalog {
  image: Model[];
  llm: Model[];
}

export function isCloud(m: Model): boolean {
  return m.engine === "cloud-openrouter" || m.engine === "cloud-openai";
}

// A sensible default GenSpec. Spread and override per-mode.
export function defaultGenSpec(): GenSpec {
  return {
    version: 1,
    mode: "txt2img",
    model: null,
    llm_model: null,
    prompt: "",
    negative_prompt: "",
    width: 1024,
    height: 1024,
    steps: null,
    cfg: null,
    sampler: null,
    scheduler: null,
    seed: null,
    batch: 1,
    denoise: 1,
    source_asset: null,
    mask_asset: null,
    reference_images: [],
    controlnet_type: null,
    controlnet_strength: 0.8,
    loras: [],
    upscale: false,
    remove_bg: false,
  };
}
