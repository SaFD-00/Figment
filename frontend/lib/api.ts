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
