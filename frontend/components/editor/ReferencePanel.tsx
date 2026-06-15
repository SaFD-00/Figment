"use client";

// "Add Ref" panel (modal). Upload a reference image, choose a sub-mode, enter a
// prompt, and generate. Each sub-mode maps to a specific GenSpec shape.

import { useRef, useState } from "react";
import { uploadFile } from "../../lib/api";
import { useEditorStore } from "../../lib/store";
import { useJobRunner } from "../../lib/useJob";
import { defaultGenSpec, type GenSpec } from "../../lib/types";
import { Button } from "../ui/Button";
import { Spinner } from "../ui/Spinner";

type SubMode = "style" | "structure" | "edit";

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
  assetId: string,
  prompt: string,
): GenSpec {
  const spec = defaultGenSpec();
  spec.prompt = prompt.trim();
  if (subMode === "style") {
    spec.mode = "reference";
    spec.model = "redux";
    spec.reference_images = [{ asset: assetId, role: "style", strength: 0.8 }];
  } else if (subMode === "structure") {
    spec.mode = "controlnet";
    spec.model = "pony-v6";
    spec.controlnet_type = "canny";
    spec.reference_images = [
      { asset: assetId, role: "structure", strength: 0.8 },
    ];
  } else {
    spec.mode = "edit";
    spec.model = "kontext";
    spec.reference_images = [{ asset: assetId, role: "edit", strength: 0.85 }];
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
  const [file, setFile] = useState<File | null>(null);
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const { run } = useJobRunner();
  const setMaskMode = useEditorStore((s) => s.setMaskMode);

  async function handleGenerate() {
    if (busy) return;
    if (!file) {
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
      const asset = await uploadFile(
        projectId,
        "reference",
        file,
        file.name,
      );
      const spec = buildSpec(subMode, asset.id, prompt);
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
        <p className="mb-4 text-xs text-muted">
          {SUBMODES.find((s) => s.id === subMode)?.desc}
        </p>

        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          className="mb-3 flex w-full items-center justify-center rounded-xl border border-dashed border-line bg-zinc-50 py-5 text-sm text-muted hover:border-accent hover:text-accent"
        >
          {file ? (
            <span className="font-medium text-ink">{file.name}</span>
          ) : (
            "Click to upload reference"
          )}
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => {
            setFile(e.target.files?.[0] ?? null);
            setError(null);
          }}
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
