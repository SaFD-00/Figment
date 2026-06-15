"use client";

// Determinate progress overlay shown on top of the canvas while a job runs.
// Shows progress * 100%, the active node label, and a live preview image.
// No indeterminate spinners — local generation is slow, so we always show
// concrete progress.

import { useEditorStore } from "../../lib/store";

export function ProgressOverlay() {
  const job = useEditorStore((s) => s.activeJob);
  if (!job) return null;

  const pct = Math.round((job.progress ?? 0) * 100);
  const isError = job.status === "error";

  return (
    <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-white/70 backdrop-blur-sm">
      {job.previewB64 && !isError && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={
            job.previewB64.startsWith("data:")
              ? job.previewB64
              : `data:image/png;base64,${job.previewB64}`
          }
          alt="preview"
          className="absolute inset-0 h-full w-full object-contain opacity-60"
        />
      )}

      <div className="relative z-10 w-4/5 max-w-sm rounded-2xl border border-line bg-white/95 p-4 shadow-soft">
        {isError ? (
          <p className="text-center text-sm font-medium text-red-600">
            {job.error || "Generation failed"}
          </p>
        ) : (
          <>
            <div className="mb-2 flex items-center justify-between text-sm">
              <span className="font-medium text-ink">
                {job.status === "queued" ? "Queued…" : "Generating…"}
              </span>
              <span className="tabular-nums text-muted">{pct}%</span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-line">
              <div
                className="h-full rounded-full bg-accent transition-[width] duration-200 ease-out"
                style={{ width: `${pct}%` }}
              />
            </div>
            <p className="mt-2 truncate text-xs text-muted">
              {job.node
                ? `${job.node}${
                    job.step && job.total ? ` · ${job.step}/${job.total}` : ""
                  }`
                : "Preparing…"}
            </p>
          </>
        )}
      </div>
    </div>
  );
}
