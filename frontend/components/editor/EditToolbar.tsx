"use client";

// Top toolbar spanning the canvas area. Each action is wired to a handler
// provided by the editor page (which owns the canvas ref + job runner).

import { useState } from "react";
import { useEditorStore } from "../../lib/store";
import { Button } from "../ui/Button";
import { Spinner } from "../ui/Spinner";
import { BrushControls } from "./BrushControls";

import type { ExportFormat } from "../../lib/api";

export interface ToolbarActions {
  onToggleMask: () => void;
  onClearMask: () => void;
  onTextEdit: (prompt: string) => void;
  onUpscale: () => void;
  onWhiteBg: () => void;
  onAddRef: () => void;
  onExport: (fmt: ExportFormat) => void;
}

export function EditToolbar(props: ToolbarActions) {
  const maskMode = useEditorStore((s) => s.maskMode);
  const currentAsset = useEditorStore((s) => s.currentAsset);
  const activeJob = useEditorStore((s) => s.activeJob);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [textEditOpen, setTextEditOpen] = useState(false);
  const [textEditPrompt, setTextEditPrompt] = useState("");
  const [exportOpen, setExportOpen] = useState(false);

  const noImage = !currentAsset;
  const jobRunning =
    activeJob?.status === "running" || activeJob?.status === "queued";
  const disabled = noImage || jobRunning;

  async function wrap(name: string, fn: () => void | Promise<void>) {
    setBusyAction(name);
    try {
      await fn();
    } finally {
      setBusyAction(null);
    }
  }

  return (
    <div className="border-b border-line bg-white">
      <div className="flex flex-wrap items-center gap-2 px-3 py-2">
        <Button
          size="sm"
          variant={maskMode ? "primary" : "secondary"}
          onClick={props.onToggleMask}
          disabled={noImage}
        >
          {maskMode ? "Exit Region Redraw" : "Region Redraw"}
        </Button>

        <Button
          size="sm"
          variant="secondary"
          onClick={() => setTextEditOpen((v) => !v)}
          disabled={disabled}
        >
          Text Edit
        </Button>

        <Button
          size="sm"
          variant="secondary"
          onClick={() => void wrap("upscale", props.onUpscale)}
          disabled={disabled}
        >
          {busyAction === "upscale" && <Spinner />}
          Upscale
        </Button>

        <Button
          size="sm"
          variant="secondary"
          onClick={() => void wrap("whitebg", props.onWhiteBg)}
          disabled={disabled}
        >
          {busyAction === "whitebg" && <Spinner />}
          White BG
        </Button>

        <Button
          size="sm"
          variant="secondary"
          onClick={props.onAddRef}
          disabled={jobRunning}
        >
          Add Ref
        </Button>

        <div className="relative ml-auto">
          <Button
            size="sm"
            variant="secondary"
            onClick={() => setExportOpen((v) => !v)}
            disabled={noImage}
          >
            {busyAction === "export" && <Spinner />}
            Export ▾
          </Button>
          {exportOpen && !noImage && (
            <div className="absolute right-0 z-20 mt-1 w-44 overflow-hidden rounded-xl border border-line bg-white shadow-soft">
              {([
                ["png", "PNG (raster)"],
                ["svg", "SVG (editable vector)"],
                ["pptx", "PPTX (slides)"],
              ] as [ExportFormat, string][]).map(([fmt, label]) => (
                <button
                  key={fmt}
                  type="button"
                  className="block w-full px-3 py-2 text-left text-sm text-ink hover:bg-accent-soft"
                  onClick={() => {
                    setExportOpen(false);
                    void wrap("export", () => props.onExport(fmt));
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Brush controls only in mask mode */}
      {maskMode && (
        <div className="px-3 pb-2">
          <BrushControls onClear={props.onClearMask} />
        </div>
      )}

      {/* Inline text-edit prompt */}
      {textEditOpen && !maskMode && (
        <div className="flex items-center gap-2 border-t border-line px-3 py-2">
          <input
            value={textEditPrompt}
            onChange={(e) => setTextEditPrompt(e.target.value)}
            placeholder="Describe the edit (e.g. 'make the sky purple')…"
            className="flex-1 rounded-xl border border-line bg-white px-3 py-2 text-sm focus:border-accent focus:outline-none"
            onKeyDown={(e) => {
              if (e.key === "Enter" && textEditPrompt.trim()) {
                props.onTextEdit(textEditPrompt.trim());
                setTextEditPrompt("");
                setTextEditOpen(false);
              }
            }}
          />
          <Button
            size="md"
            variant="primary"
            disabled={disabled || !textEditPrompt.trim()}
            onClick={() => {
              props.onTextEdit(textEditPrompt.trim());
              setTextEditPrompt("");
              setTextEditOpen(false);
            }}
          >
            Apply
          </Button>
        </div>
      )}
    </div>
  );
}
