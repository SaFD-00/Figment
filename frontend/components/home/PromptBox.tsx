"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ModeTabs, type HomeMode } from "./ModeTabs";
import { Button } from "../ui/Button";
import { Spinner } from "../ui/Spinner";
import { ModelPillRow } from "../models/ModelPicker";
import { useModelsStore } from "../../lib/models";
import {
  createJob,
  createProject,
  enhancePrompt,
  fileToDataUrl,
  uploadFile,
} from "../../lib/api";
import { defaultGenSpec, type GenMode } from "../../lib/types";
import { refCap } from "../../lib/constants";
import { firstWords } from "../../lib/format";

const PLACEHOLDERS: Record<HomeMode, string> = {
  generate: "Describe the figure or image you want to create…",
  edit: "Upload an image, then describe how to change it…",
  reference: "Upload a reference, then describe what to make from it…",
  figure: "Describe a diagram or figure — exported as editable SVG/PPTX (cloud)…",
};

export function PromptBox() {
  const router = useRouter();
  const [mode, setMode] = useState<HomeMode>("generate");
  const [prompt, setPrompt] = useState("");
  const getImageModelForMode = useModelsStore((s) => s.getImageModelForMode);
  // Subscribe to the resolved Model for reference mode so the cap reacts to model switches.
  const refModel = useModelsStore((s) => s.selectedImageForMode("reference"));
  const selectedLlmId = useModelsStore((s) => s.selectedLlmId);
  const selectedLlm = useModelsStore((s) => s.selectedLlm);
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [enhancing, setEnhancing] = useState(false);
  const [enhanceNote, setEnhanceNote] = useState(""); // optional "how to enhance" guidance
  const [prevPrompt, setPrevPrompt] = useState<string | null>(null); // original kept for undo
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const showDropzone = mode === "edit" || mode === "reference";
  // Edit consumes a single source image; reference accepts up to the selected model's cap
  // (local qwen-edit → 3, cloud → 6).
  const isLocalRef = mode === "reference" && refModel?.engine === "local-comfy";
  const maxFiles = mode === "reference" ? refCap(refModel) : 1;

  // Switching to a lower-cap model (e.g. cloud → local) trims any now-excess uploads.
  useEffect(() => {
    setFiles((prev) => (prev.length > maxFiles ? prev.slice(0, maxFiles) : prev));
  }, [maxFiles]);

  const genMode: GenMode = useMemo(() => {
    if (mode === "edit") return "img2img";
    if (mode === "reference") return "reference";
    if (mode === "figure") return "figure";
    return "txt2img";
  }, [mode]);

  async function handleGenerate() {
    if (busy) return;
    if (!prompt.trim()) {
      setError("Enter a prompt first.");
      return;
    }
    if (showDropzone && files.length === 0) {
      setError("Upload an image first.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      const project = await createProject(firstWords(prompt));

      const spec = defaultGenSpec();
      spec.mode = genMode;
      spec.model = getImageModelForMode(genMode);
      spec.llm_model = selectedLlmId || null;
      spec.prompt = prompt.trim();

      if (mode === "edit" && files[0]) {
        const asset = await uploadFile(project.id, "source", files[0], files[0].name);
        spec.source_asset = asset.id;
      } else if (mode === "reference") {
        spec.reference_images = [];
        for (const f of files) {
          const a = await uploadFile(project.id, "reference", f, f.name);
          spec.reference_images.push({ asset: a.id, role: "style", strength: 0.8 });
        }
      }

      const job = await createJob(project.id, spec);
      router.push(`/editor/${project.id}?job=${job.id}`);
    } catch (e) {
      setError((e as Error)?.message ?? "Something went wrong.");
      setBusy(false);
    }
  }

  async function handleEnhance() {
    if (enhancing || busy) return;
    const text = prompt.trim();
    if (!text) {
      setError("Enter a prompt first.");
      return;
    }
    setError(null);
    setEnhancing(true);
    try {
      // Edit/reference modes feed the uploaded image to a vision LLM so it can ground the rewrite;
      // first image only (matches the reference/edit generation convention).
      const image =
        showDropzone && files[0] && selectedLlm()?.vision
          ? await fileToDataUrl(files[0])
          : null;
      const { prompt: enhanced } = await enhancePrompt(text, {
        llmModel: selectedLlmId,
        imageModel: getImageModelForMode(genMode),
        instruction: enhanceNote.trim() || null,
        image,
      });
      setPrevPrompt(prompt); // remember the original (untrimmed) for undo
      setPrompt(enhanced);
    } catch (e) {
      setError((e as Error)?.message ?? "Enhance failed.");
    } finally {
      setEnhancing(false);
    }
  }

  function handleUndo() {
    if (prevPrompt === null) return;
    setPrompt(prevPrompt);
    setPrevPrompt(null);
  }

  function onPickFile(e: React.ChangeEvent<HTMLInputElement>) {
    const picked = Array.from(e.target.files ?? []);
    setFiles((prev) => [...prev, ...picked].slice(0, maxFiles));
    setError(null);
    e.target.value = ""; // allow re-selecting the same file
  }

  function removeFile(idx: number) {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
  }

  return (
    <div className="w-full">
      <div className="mb-4 flex justify-center">
        <ModeTabs mode={mode} onChange={(m) => { setMode(m); setFiles([]); setError(null); }} />
      </div>

      <div className="rounded-2xl border border-line bg-panel p-3 shadow-soft">
        <textarea
          value={prompt}
          onChange={(e) => {
            setPrompt(e.target.value);
            if (prevPrompt !== null) setPrevPrompt(null); // editing drops the undo offer
          }}
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
            {files.length < maxFiles && (
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-line bg-zinc-50 py-4 text-sm text-muted transition-colors hover:border-accent hover:text-accent"
              >
                {mode === "reference"
                  ? `Click to add a reference (${files.length}/${maxFiles})`
                  : "Click to upload an image"}
              </button>
            )}
            {isLocalRef && (
              <p className="mt-2 px-1 text-xs text-muted">
                Local model uses up to {maxFiles} reference images.
              </p>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              multiple={mode === "reference"}
              className="hidden"
              onChange={onPickFile}
            />
          </div>
        )}

        <div className="border-t border-line px-2 pt-2">
          <input
            type="text"
            value={enhanceNote}
            onChange={(e) => setEnhanceNote(e.target.value)}
            placeholder="How to enhance (optional) — e.g. more cinematic, neon lighting"
            className="w-full bg-transparent px-1 py-1 text-sm text-ink placeholder:text-muted focus:outline-none"
          />
          {showDropzone && files.length > 0 && selectedLlm()?.vision && (
            <p className="px-1 pb-1 text-xs text-muted">
              🖼 your uploaded image will be sent to the LLM
            </p>
          )}
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-line px-2 pt-3">
          <ModelPillRow mode={genMode} className="flex min-w-0 flex-wrap items-center gap-2" />

          <div className="flex shrink-0 items-center gap-2">
            {prevPrompt !== null && (
              <Button
                variant="ghost"
                size="md"
                onClick={handleUndo}
                disabled={enhancing || busy}
                title="Restore your original prompt"
              >
                ↶ Undo
              </Button>
            )}
            <Button
              variant="secondary"
              size="md"
              onClick={() => void handleEnhance()}
              disabled={enhancing || busy || !prompt.trim()}
              title="Let the selected LLM expand your prompt into rich detail"
            >
              {enhancing && <Spinner />}
              {enhancing ? "Enhancing…" : "Enhance"}
            </Button>
            <Button
              variant="primary"
              size="md"
              onClick={() => void handleGenerate()}
              disabled={busy || enhancing}
            >
              {busy && <Spinner />}
              {busy ? "Starting…" : "Generate"}
            </Button>
          </div>
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
