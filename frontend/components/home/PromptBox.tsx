"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "../ui/Button";
import { Spinner } from "../ui/Spinner";
import { ModelPill } from "../models/ModelPicker";
import { useModelsStore } from "../../lib/models";
import { useEditorStore } from "../../lib/store";
import {
  createProject,
  enhancePrompt,
  fileToDataUrl,
  uploadFile,
} from "../../lib/api";
import { MAX_REFERENCE_IMAGES } from "../../lib/constants";
import { firstWords } from "../../lib/format";

// Single entry point: the user types a prompt and (optionally) attaches image(s). There is no mode
// selection here — the chat LLM in the editor routes the request to the right mode (generate / edit /
// reference / figure), asking a clarifying question first if it's ambiguous. Submitting just stages
// the prompt + uploads and hands off to the editor, where the first chat turn drives generation.
const PLACEHOLDER =
  "Describe the figure or image you want — or attach an image to edit or use as a reference…";

export function PromptBox() {
  const router = useRouter();
  const [prompt, setPrompt] = useState("");
  const getImageModelForMode = useModelsStore((s) => s.getImageModelForMode);
  const selectedLlmId = useModelsStore((s) => s.selectedLlmId);
  const setPendingStart = useEditorStore((s) => s.setPendingStart);
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [enhancing, setEnhancing] = useState(false);
  const [enhanceNote, setEnhanceNote] = useState(""); // optional "how to enhance" guidance
  const [prevPrompt, setPrevPrompt] = useState<string | null>(null); // original kept for undo
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const maxFiles = MAX_REFERENCE_IMAGES;

  // Trim any now-excess uploads if the cap ever shrinks (defensive; cap is currently constant).
  useEffect(() => {
    setFiles((prev) => (prev.length > maxFiles ? prev.slice(0, maxFiles) : prev));
  }, [maxFiles]);

  async function handleStart() {
    if (busy) return;
    if (!prompt.trim() && files.length === 0) {
      setError("Enter a prompt or attach an image first.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      const project = await createProject(firstWords(prompt) || "Untitled");

      // Upload every attachment as a neutral "reference" asset (a valid upload kind). The backend
      // binds these ids to source_asset vs reference_images based on the mode the LLM routes to.
      const attachments: { asset: string }[] = [];
      for (const f of files) {
        const a = await uploadFile(project.id, "reference", f, f.name);
        attachments.push({ asset: a.id });
      }

      // Hand off to the editor; ChatPanel auto-sends this as the first chat turn (which routes mode).
      setPendingStart({ prompt: prompt.trim(), attachments });
      router.push(`/editor/${project.id}`);
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
      // All chat LLMs are vision-capable: if an image is attached, feed the first one so the rewrite
      // is grounded in what it shows. Mode is unknown here, so use the txt2img model for the style hint.
      const image = files[0] ? await fileToDataUrl(files[0]) : null;
      const { prompt: enhanced } = await enhancePrompt(text, {
        llmModel: selectedLlmId,
        imageModel: getImageModelForMode("txt2img"),
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
      <div className="rounded-2xl border border-line bg-panel p-3 shadow-soft">
        <textarea
          value={prompt}
          onChange={(e) => {
            setPrompt(e.target.value);
            if (prevPrompt !== null) setPrevPrompt(null); // editing drops the undo offer
          }}
          placeholder={PLACEHOLDER}
          rows={4}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
              e.preventDefault();
              void handleStart();
            }
          }}
          className="w-full resize-none bg-transparent px-2 py-1.5 text-base text-ink placeholder:text-muted focus:outline-none"
        />

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
              {files.length > 0
                ? `Add another image (${files.length}/${maxFiles})`
                : "Optionally attach an image to edit or reference"}
            </button>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            multiple
            className="hidden"
            onChange={onPickFile}
          />
        </div>

        <div className="border-t border-line px-2 pt-2">
          <input
            type="text"
            value={enhanceNote}
            onChange={(e) => setEnhanceNote(e.target.value)}
            placeholder="How to enhance (optional) — e.g. more cinematic, neon lighting"
            className="w-full bg-transparent px-1 py-1 text-sm text-ink placeholder:text-muted focus:outline-none"
          />
          {files.length > 0 && (
            <p className="px-1 pb-1 text-xs text-muted">
              🖼 your attached image will be sent to the LLM
            </p>
          )}
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-line px-2 pt-3">
          <ModelPill kind="llm" />

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
              onClick={() => void handleStart()}
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
        Tip: press ⌘/Ctrl + Enter to start. The assistant picks the right mode — and asks if it's unsure.
      </p>
    </div>
  );
}
