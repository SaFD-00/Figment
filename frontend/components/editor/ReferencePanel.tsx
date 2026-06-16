"use client";

// "Add Ref" panel (modal). Upload a reference image, choose a sub-mode, enter a
// prompt, and generate. Each sub-mode maps to a specific GenSpec shape.

import { useRef, useState } from "react";
import { uploadFile } from "../../lib/api";
import { useEditorStore } from "../../lib/store";
import { useModelsStore } from "../../lib/models";
import { useJobRunner } from "../../lib/useJob";
import {
  defaultGenSpec,
  type GenMode,
  type GenSpec,
  type ReferenceImage,
} from "../../lib/types";
import { MAX_REFERENCE_IMAGES } from "../../lib/constants";
import { ModelPill } from "../models/ModelPicker";
import { Button } from "../ui/Button";
import { Spinner } from "../ui/Spinner";

type SubMode = "style" | "structure" | "edit";

// Each reference sub-mode maps to a generation mode, which drives per-mode model selection.
const SUBMODE_MODE: Record<SubMode, GenMode> = {
  style: "reference",
  structure: "controlnet",
  edit: "edit",
};

const SUBMODES: { id: SubMode; label: string; desc: string }[] = [
  { id: "style", label: "Style", desc: "Match the look/style of the reference" },
  {
    id: "structure",
    label: "Structure",
    desc: "Follow the composition (ControlNet canny)",
  },
  { id: "edit", label: "Edit this", desc: "Edit the reference directly" },
];

function buildSpec(
  subMode: SubMode,
  assetIds: string[],
  prompt: string,
  model: string | null,
): GenSpec {
  const spec = defaultGenSpec();
  spec.prompt = prompt.trim();
  spec.mode = SUBMODE_MODE[subMode];
  spec.model = model;
  if (subMode === "style") {
    spec.reference_images = assetIds.map(
      (id): ReferenceImage => ({ asset: id, role: "style", strength: 0.8 }),
    );
  } else if (subMode === "structure") {
    spec.controlnet_type = "canny";
    spec.reference_images = assetIds.map(
      (id): ReferenceImage => ({ asset: id, role: "structure", strength: 0.8 }),
    );
  } else {
    spec.reference_images = assetIds.map(
      (id): ReferenceImage => ({ asset: id, role: "edit", strength: 0.85 }),
    );
  }
  return spec;
}

export function ReferencePanel({
  projectId,
  onClose,
}: {
  projectId: string;
  onClose: () => void;
}) {
  const [subMode, setSubMode] = useState<SubMode>("style");
  const [files, setFiles] = useState<File[]>([]);
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const { run } = useJobRunner();
  const setMaskMode = useEditorStore((s) => s.setMaskMode);
  const getImageModelForMode = useModelsStore((s) => s.getImageModelForMode);

  function onPickFile(e: React.ChangeEvent<HTMLInputElement>) {
    const picked = Array.from(e.target.files ?? []);
    setFiles((prev) => [...prev, ...picked].slice(0, MAX_REFERENCE_IMAGES));
    setError(null);
    e.target.value = ""; // allow re-selecting the same file
  }

  function removeFile(idx: number) {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
  }

  async function handleGenerate() {
    if (busy) return;
    if (files.length === 0) {
      setError("Upload a reference image.");
      return;
    }
    if (!prompt.trim()) {
      setError("Enter a prompt.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      const assetIds: string[] = [];
      for (const f of files) {
        const asset = await uploadFile(projectId, "reference", f, f.name);
        assetIds.push(asset.id);
      }
      const spec = buildSpec(
        subMode,
        assetIds,
        prompt,
        getImageModelForMode(SUBMODE_MODE[subMode]),
      );
      setMaskMode(false);
      await run(projectId, spec, { pushUndo: true });
      onClose();
    } catch (e) {
      setError((e as Error)?.message ?? "Failed to start.");
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-2xl border border-line bg-white p-5 shadow-soft"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-base font-semibold text-ink">Add reference</h3>
          <button
            type="button"
            onClick={onClose}
            className="text-muted hover:text-ink"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <div className="mb-4 grid grid-cols-3 gap-2">
          {SUBMODES.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => setSubMode(s.id)}
              className={`rounded-xl border px-2 py-2 text-xs font-medium transition-colors ${
                subMode === s.id
                  ? "border-accent bg-accent-soft text-accent"
                  : "border-line text-muted hover:text-ink"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
        <div className="mb-4 flex items-center justify-between gap-2">
          <p className="text-xs text-muted">
            {SUBMODES.find((s) => s.id === subMode)?.desc}
          </p>
          <ModelPill kind="image" mode={SUBMODE_MODE[subMode]} placement="bottom" />
        </div>

        {files.length > 0 && (
          <ul className="mb-2 flex flex-col gap-1">
            {files.map((f, i) => (
              <li
                key={`${f.name}-${i}`}
                className="flex items-center justify-between gap-2 rounded-lg border border-line bg-white px-3 py-1.5 text-sm"
              >
                <span className="truncate font-medium text-ink">{f.name}</span>
                <button
                  type="button"
                  onClick={() => removeFile(i)}
                  className="shrink-0 text-muted hover:text-red-600"
                  aria-label={`Remove ${f.name}`}
                >
                  ✕
                </button>
              </li>
            ))}
          </ul>
        )}
        {files.length < MAX_REFERENCE_IMAGES && (
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            className="mb-3 flex w-full items-center justify-center rounded-xl border border-dashed border-line bg-zinc-50 py-5 text-sm text-muted hover:border-accent hover:text-accent"
          >
            {files.length === 0
              ? "Click to upload reference"
              : `Add another reference (${files.length}/${MAX_REFERENCE_IMAGES})`}
          </button>
        )}
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          onChange={onPickFile}
        />

        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={3}
          placeholder="Describe what to make…"
          className="mb-3 w-full resize-none rounded-xl border border-line bg-white px-3 py-2 text-sm focus:border-accent focus:outline-none"
        />

        {error && <p className="mb-3 text-xs text-red-600">{error}</p>}

        <div className="flex justify-end gap-2">
          <Button variant="ghost" size="md" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="md"
            onClick={() => void handleGenerate()}
            disabled={busy}
          >
            {busy && <Spinner />}
            Generate
          </Button>
        </div>
      </div>
    </div>
  );
}
