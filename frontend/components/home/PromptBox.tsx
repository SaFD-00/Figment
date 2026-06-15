"use client";

import { useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ModeTabs, type HomeMode } from "./ModeTabs";
import { Button } from "../ui/Button";
import { Spinner } from "../ui/Spinner";
import { ModelSelect } from "../models/ModelPicker";
import { useModelsStore } from "../../lib/models";
import {
  createJob,
  createProject,
  uploadFile,
} from "../../lib/api";
import { defaultGenSpec, type GenMode } from "../../lib/types";
import { firstWords } from "../../lib/format";

const PLACEHOLDERS: Record<HomeMode, string> = {
  generate: "Describe the figure or image you want to create…",
  edit: "Upload an image, then describe how to change it…",
  reference: "Upload a reference, then describe what to make from it…",
};

export function PromptBox() {
  const router = useRouter();
  const [mode, setMode] = useState<HomeMode>("generate");
  const [prompt, setPrompt] = useState("");
  const selectedImageId = useModelsStore((s) => s.selectedImageId);
  const selectedLlmId = useModelsStore((s) => s.selectedLlmId);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const showDropzone = mode === "edit" || mode === "reference";

  const genMode: GenMode = useMemo(() => {
    if (mode === "edit") return "img2img";
    if (mode === "reference") return "reference";
    return "txt2img";
  }, [mode]);

  async function handleGenerate() {
    if (busy) return;
    if (!prompt.trim()) {
      setError("Enter a prompt first.");
      return;
    }
    if (showDropzone && !file) {
      setError("Upload an image first.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      const project = await createProject(firstWords(prompt));

      const spec = defaultGenSpec();
      spec.mode = genMode;
      spec.model = selectedImageId || null;
      spec.llm_model = selectedLlmId || null;
      spec.prompt = prompt.trim();

      if (file && mode === "edit") {
        const asset = await uploadFile(project.id, "source", file, file.name);
        spec.source_asset = asset.id;
      } else if (file && mode === "reference") {
        const asset = await uploadFile(
          project.id,
          "reference",
          file,
          file.name,
        );
        spec.reference_images = [
          { asset: asset.id, role: "style", strength: 0.8 },
        ];
      }

      const job = await createJob(project.id, spec);
      router.push(`/editor/${project.id}?job=${job.id}`);
    } catch (e) {
      setError((e as Error)?.message ?? "Something went wrong.");
      setBusy(false);
    }
  }

  function onPickFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] ?? null;
    setFile(f);
    setError(null);
  }

  return (
    <div className="w-full">
      <div className="mb-4 flex justify-center">
        <ModeTabs mode={mode} onChange={(m) => { setMode(m); setError(null); }} />
      </div>

      <div className="rounded-2xl border border-line bg-panel p-3 shadow-soft">
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder={PLACEHOLDERS[mode]}
          rows={4}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
              e.preventDefault();
              void handleGenerate();
            }
          }}
          className="w-full resize-none bg-transparent px-2 py-1.5 text-base text-ink placeholder:text-muted focus:outline-none"
        />

        {showDropzone && (
          <div className="px-2 pb-2">
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-line bg-zinc-50 py-4 text-sm text-muted transition-colors hover:border-accent hover:text-accent"
            >
              {file ? (
                <span className="font-medium text-ink">{file.name}</span>
              ) : (
                <>
                  <span>Click to upload an image</span>
                </>
              )}
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={onPickFile}
            />
          </div>
        )}

        <div className="flex items-center justify-between gap-3 border-t border-line px-2 pt-3">
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-sm text-muted">
              <span className="hidden sm:inline">Image</span>
              <ModelSelect kind="image" />
            </label>
            <label className="flex items-center gap-2 text-sm text-muted">
              <span className="hidden sm:inline">LLM</span>
              <ModelSelect kind="llm" />
            </label>
          </div>

          <Button
            variant="primary"
            size="md"
            onClick={() => void handleGenerate()}
            disabled={busy}
          >
            {busy && <Spinner />}
            {busy ? "Starting…" : "Generate"}
          </Button>
        </div>
      </div>

      {error && (
        <p className="mt-3 text-center text-sm text-red-600">{error}</p>
      )}
      <p className="mt-3 text-center text-xs text-muted">
        Tip: press ⌘/Ctrl + Enter to generate.
      </p>
    </div>
  );
}
