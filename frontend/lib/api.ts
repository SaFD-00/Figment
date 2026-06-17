// Typed fetch wrappers for the backend JSON API.
// All requests go through the Next.js proxy at /api/* -> http://127.0.0.1:8000/*

import type {
  Asset,
  AssetKind,
  ChatMessage,
  GenSpec,
  Job,
  Model,
  ModelCatalog,
  Project,
} from "./types";

const BASE = "/api";

async function jfetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = (body && (body.detail || body.error)) || detail;
    } catch {
      /* ignore non-json error bodies */
    }
    throw new Error(`${res.status} ${detail}`);
  }
  // Some endpoints (e.g. cancel) may return empty body.
  const text = await res.text();
  return (text ? JSON.parse(text) : (undefined as unknown)) as T;
}

// ---------- Projects ----------
export const createProject = (title: string) =>
  jfetch<Project>("/projects", {
    method: "POST",
    body: JSON.stringify({ title }),
  });

export const listProjects = () => jfetch<Project[]>("/projects");

export const getProject = (id: string) => jfetch<Project>(`/projects/${id}`);

export const updateProject = (id: string, title: string) =>
  jfetch<Project>(`/projects/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });

export const deleteProject = (id: string) =>
  jfetch<void>(`/projects/${id}`, { method: "DELETE" });

export const getMessages = (id: string) =>
  jfetch<ChatMessage[]>(`/projects/${id}/messages`);

export const getProjectAssets = (id: string) =>
  jfetch<Asset[]>(`/projects/${id}/assets`);

// ---------- Jobs ----------
export const createJob = (projectId: string, genspec: GenSpec) =>
  jfetch<Job>("/jobs", {
    method: "POST",
    body: JSON.stringify({ project_id: projectId, genspec }),
  });

export const getJob = (id: string) => jfetch<Job>(`/jobs/${id}`);

export const cancelJob = (id: string) =>
  jfetch<void>(`/jobs/${id}/cancel`, { method: "POST" });

// ---------- Assets ----------
export const getAsset = (id: string) => jfetch<Asset>(`/assets/${id}`);

export const assetFileUrl = (id: string) => `${BASE}/assets/${id}/file`;

// Export / Vectorize: download an asset as png | svg | pptx.
export type ExportFormat = "png" | "svg" | "pptx";
export const assetExportUrl = (id: string, fmt: ExportFormat) =>
  `${BASE}/assets/${id}/export?fmt=${fmt}`;

export interface AssetFormats {
  png: boolean;
  svg: boolean;
  pptx: boolean;
  is_figure: boolean;
}
export const getAssetFormats = (id: string) =>
  jfetch<AssetFormats>(`/assets/${id}/formats`);

export const upscaleAsset = (id: string) =>
  jfetch<Asset>(`/assets/${id}/upscale`, { method: "POST" });

export const whitebgAsset = (id: string) =>
  jfetch<Asset>(`/assets/${id}/whitebg`, { method: "POST" });

export const removebgAsset = (id: string) =>
  jfetch<Asset>(`/assets/${id}/removebg`, { method: "POST" });

// ---------- Models ----------
export const listModels = () => jfetch<Model[]>("/models");

// Unified catalog (image + llm) for the model picker.
export const listAllModels = () => jfetch<ModelCatalog>("/models/all");

export const listLlmModels = () => jfetch<Model[]>("/models/llm");

// ---------- Prompt ----------
// Upgrade a short/vague idea into a rich English image-generation prompt via the selected LLM.
// `instruction` is optional "how to enhance" guidance; `image` (a data URL) lets a vision LLM
// ground the rewrite in an uploaded edit/reference image.
export async function enhancePrompt(
  prompt: string,
  opts?: {
    llmModel?: string | null;
    imageModel?: string | null;
    instruction?: string | null;
    image?: string | null;
  },
): Promise<{ prompt: string }> {
  const body = JSON.stringify({
    prompt,
    llm_model: opts?.llmModel ?? null,
    image_model: opts?.imageModel ?? null,
    instruction: opts?.instruction ?? null,
    image: opts?.image ?? null,
  });
  const call = () =>
    jfetch<{ prompt: string }>("/prompt/enhance", { method: "POST", body });
  try {
    return await call();
  } catch {
    // A local LLM's first enhance is usually a cold load: the dev proxy resets at ~30s
    // (surfacing as a 5xx / network error), but that attempt still kicked off the model load,
    // which Ollama keeps warm. Retry once after a short pause to land on the now-warm model.
    await new Promise((r) => setTimeout(r, 1500));
    try {
      return await call();
    } catch (err) {
      const msg = (err as Error)?.message ?? "";
      // Proxy reset / gateway timeout / network error → no useful detail; show a clear hint.
      // A real backend error (e.g. 502 "Enhance failed: …") keeps its own message.
      if (/^50[034]/.test(msg) || /failed to fetch/i.test(msg) || msg === "") {
        throw new Error(
          "Prompt enhance timed out — the model may still be loading. Try again.",
        );
      }
      throw err;
    }
  }
}

// Read a File/Blob into a base64 data URL (e.g. to attach an image to prompt-enhance).
export const fileToDataUrl = (file: Blob): Promise<string> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(reader.error ?? new Error("Failed to read file"));
    reader.readAsDataURL(file);
  });

// ---------- Uploads ----------
export async function uploadFile(
  projectId: string,
  kind: AssetKind,
  file: Blob,
  filename = "upload.png",
): Promise<Asset> {
  const form = new FormData();
  form.append("project_id", projectId);
  form.append("kind", kind);
  form.append("file", file, filename);
  const res = await fetch(`${BASE}/uploads`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    throw new Error(`Upload failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as Asset;
}
