"use client";

// Thumbnail strip of this project's output assets. Clicking one makes it the
// current canvas image. Also exposes Undo (revert to previous image).

import { useCallback, useEffect, useState } from "react";
import { assetFileUrl, getProjectAssets } from "../../lib/api";
import { hideBrokenImage } from "../../lib/img";
import { useEditorStore } from "../../lib/store";
import type { Asset } from "../../lib/types";
import { Button } from "../ui/Button";

const OUTPUT_KINDS = new Set(["output", "upscaled", "nobg"]);

export function HistoryStrip({ projectId }: { projectId: string }) {
  const [assets, setAssets] = useState<Asset[]>([]);
  const currentAsset = useEditorStore((s) => s.currentAsset);
  const setCurrentAsset = useEditorStore((s) => s.setCurrentAsset);
  const undo = useEditorStore((s) => s.undo);
  const undoStack = useEditorStore((s) => s.undoStack);
  const activeJob = useEditorStore((s) => s.activeJob);

  const refresh = useCallback(() => {
    getProjectAssets(projectId)
      .then((all) => {
        const outputs = all
          .filter((a) => OUTPUT_KINDS.has(a.kind))
          .sort(
            (a, b) =>
              new Date(b.created_at).getTime() -
              new Date(a.created_at).getTime(),
          );
        setAssets(outputs);
      })
      .catch(() => {
        /* ignore */
      });
  }, [projectId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Refresh when a job finishes (currentAsset changes) so new outputs appear.
  useEffect(() => {
    if (!activeJob) refresh();
  }, [activeJob, refresh]);

  return (
    <div className="flex items-center gap-3 border-t border-line bg-white px-3 py-2">
      <Button
        size="sm"
        variant="secondary"
        onClick={undo}
        disabled={undoStack.length === 0}
        title="Revert to previous image"
      >
        ↶ Undo
      </Button>

      <div className="flex flex-1 items-center gap-2 overflow-x-auto">
        {assets.length === 0 && (
          <span className="px-1 text-xs text-muted">No outputs yet.</span>
        )}
        {assets.map((a) => {
          const active = currentAsset?.id === a.id;
          return (
            <button
              key={a.id}
              type="button"
              onClick={() => setCurrentAsset(a, true)}
              className={`relative h-16 w-16 shrink-0 overflow-hidden rounded-lg border-2 transition-colors ${
                active ? "border-accent" : "border-line hover:border-muted"
              }`}
              title={a.kind}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={assetFileUrl(a.id)}
                alt={a.kind}
                onError={hideBrokenImage}
                className="h-full w-full object-cover"
              />
            </button>
          );
        })}
      </div>
    </div>
  );
}
