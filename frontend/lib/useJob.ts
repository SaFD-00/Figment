// Shared hook to start a job from a GenSpec and stream its progress into the
// editor store. On completion it loads the result asset and swaps the canvas.

"use client";

import { useCallback, useRef } from "react";
import { createJob, getAsset } from "./api";
import { jobEvents, type JobEventControl } from "./sse";
import { useEditorStore } from "./store";
import type { GenSpec } from "./types";

export interface RunJobOptions {
  // Push the previous canvas image onto the undo stack when the result arrives.
  pushUndo?: boolean;
  onDone?: (resultAssetId: string) => void;
  onError?: (message: string) => void;
}

export function useJobRunner() {
  const controlRef = useRef<JobEventControl | null>(null);
  const setActiveJob = useEditorStore((s) => s.setActiveJob);
  const updateActiveJob = useEditorStore((s) => s.updateActiveJob);
  const setCurrentAsset = useEditorStore((s) => s.setCurrentAsset);

  const attach = useCallback(
    (jobId: string, opts: RunJobOptions = {}) => {
      controlRef.current?.close();
      setActiveJob({ id: jobId, progress: 0, status: "queued" });

      controlRef.current = jobEvents(jobId, {
        onQueued: () => updateActiveJob({ status: "queued" }),
        onProgress: (p) =>
          updateActiveJob({
            status: "running",
            progress: p.progress ?? 0,
            node: p.node,
            step: p.step,
            total: p.total,
          }),
        onPreview: (b64) => updateActiveJob({ previewB64: b64 }),
        onDone: async (d) => {
          updateActiveJob({ status: "done", progress: 1 });
          try {
            const asset = await getAsset(d.result_asset);
            setCurrentAsset(asset, opts.pushUndo);
            opts.onDone?.(d.result_asset);
          } catch (e) {
            opts.onError?.((e as Error)?.message ?? "failed to load result");
          } finally {
            // Brief settle so the 100% bar is visible, then clear.
            setTimeout(() => setActiveJob(null), 400);
          }
        },
        onError: (err) => {
          updateActiveJob({ status: "error", error: err.message });
          opts.onError?.(err.message);
          setTimeout(() => setActiveJob(null), 1500);
        },
      });
    },
    [setActiveJob, updateActiveJob, setCurrentAsset],
  );

  // Create a job from a GenSpec then attach to its event stream.
  const run = useCallback(
    async (projectId: string, spec: GenSpec, opts: RunJobOptions = {}) => {
      const job = await createJob(projectId, spec);
      attach(job.id, opts);
      return job;
    },
    [attach],
  );

  return { run, attach };
}
