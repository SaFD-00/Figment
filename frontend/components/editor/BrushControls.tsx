"use client";

// Brush controls — only rendered while in mask mode.

import { useEditorStore } from "../../lib/store";
import { Button } from "../ui/Button";

export function BrushControls({ onClear }: { onClear: () => void }) {
  const brushSize = useEditorStore((s) => s.brushSize);
  const setBrushSize = useEditorStore((s) => s.setBrushSize);
  const eraser = useEditorStore((s) => s.eraser);
  const setEraser = useEditorStore((s) => s.setEraser);

  return (
    <div className="flex items-center gap-4 rounded-xl border border-line bg-white px-3 py-2 shadow-card">
      <label className="flex items-center gap-2 text-xs text-muted">
        Brush
        <input
          type="range"
          min={4}
          max={160}
          value={brushSize}
          onChange={(e) => setBrushSize(Number(e.target.value))}
          className="w-32"
        />
        <span className="w-8 tabular-nums text-ink">{brushSize}</span>
      </label>

      <div className="flex items-center gap-1">
        <Button
          size="sm"
          variant={eraser ? "secondary" : "primary"}
          onClick={() => setEraser(false)}
        >
          Brush
        </Button>
        <Button
          size="sm"
          variant={eraser ? "primary" : "secondary"}
          onClick={() => setEraser(true)}
        >
          Eraser
        </Button>
      </div>

      <Button size="sm" variant="ghost" onClick={onClear}>
        Clear
      </Button>
    </div>
  );
}
