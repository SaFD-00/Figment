"use client";

// Editor page — 3-zone layout:
//   - left:   ChatPanel (fixed width)
//   - top:    EditToolbar spanning the canvas area
//   - center: CanvasStage (flex) + HistoryStrip below
//
// This page owns the canvas ref and all toolbar action handlers, since several
// actions (region redraw, text edit) need both the canvas (to export the mask /
// current image) and the shared job runner.

import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import {
  assetExportUrl,
  assetFileUrl,
  getJob,
  getProject,
  getProjectAssets,
  upscaleAsset,
  whitebgAsset,
  uploadFile,
  type ExportFormat,
} from "../../../lib/api";
import { dataURLtoBlob } from "../../../lib/canvas";
import { useEditorStore } from "../../../lib/store";
import { useModelsStore } from "../../../lib/models";
import { useJobRunner } from "../../../lib/useJob";
import { defaultGenSpec, type Project } from "../../../lib/types";
import { ChatPanel } from "../../../components/editor/ChatPanel";
import { EditToolbar } from "../../../components/editor/EditToolbar";
import { HistoryStrip } from "../../../components/editor/HistoryStrip";
import { ReferencePanel } from "../../../components/editor/ReferencePanel";
import type { CanvasStageHandle } from "../../../components/editor/CanvasStage";
import type { ForwardRefExoticComponent, RefAttributes } from "react";

// react-konva must not be server-rendered (Konva touches `window`).
// next/dynamic drops the forwarded-ref typing, so we re-assert the component
// type to keep `ref={canvasRef}` type-safe.
const CanvasStage = dynamic(
  () =>
    import("../../../components/editor/CanvasStage").then((m) => m.CanvasStage),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full w-full items-center justify-center text-sm text-muted">
        Loading canvas…
      </div>
    ),
  },
) as ForwardRefExoticComponent<RefAttributes<CanvasStageHandle>>;

function EditorPageInner() {
  const params = useParams<{ projectId: string }>();
  const projectId = params.projectId;
  const searchParams = useSearchParams();
  const initialJob = searchParams.get("job");

  const canvasRef = useRef<CanvasStageHandle>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [refOpen, setRefOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const currentAsset = useEditorStore((s) => s.currentAsset);
  const setCurrentAsset = useEditorStore((s) => s.setCurrentAsset);
  const setCurrentProjectId = useEditorStore((s) => s.setCurrentProjectId);
  const maskMode = useEditorStore((s) => s.maskMode);
  const setMaskMode = useEditorStore((s) => s.setMaskMode);
  const setInitialPrompt = useEditorStore((s) => s.setInitialPrompt);
  const reset = useEditorStore((s) => s.reset);
  const getImageModelForMode = useModelsStore((s) => s.getImageModelForMode);

  const { run, attach } = useJobRunner();

  const flash = useCallback((msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  }, []);

  // Initialize project + current image; attach to an in-flight job if present.
  useEffect(() => {
    reset();
    setCurrentProjectId(projectId);

    getProject(projectId)
      .then(setProject)
      .catch(() => flash("Could not load project."));

    // Seed the canvas with the latest existing output asset.
    getProjectAssets(projectId)
      .then((assets) => {
        const outputs = assets
          .filter((a) => ["output", "upscaled", "nobg"].includes(a.kind))
          .sort(
            (a, b) =>
              new Date(b.created_at).getTime() -
              new Date(a.created_at).getTime(),
          );
        if (outputs[0]) setCurrentAsset(outputs[0]);
      })
      .catch(() => {
        /* none yet */
      });

    // If we navigated here with ?job=, start streaming its progress.
    if (initialJob) {
      getJob(initialJob)
        .then((job) => {
          // The originating prompt lives in the job's GenSpec — pin it to the canvas.
          setInitialPrompt(job.genspec?.prompt ?? null);
          if (job.status === "done" && job.result_asset) {
            // Already finished before we attached — just load it.
            return;
          }
          attach(initialJob, { pushUndo: false });
        })
        .catch(() => attach(initialJob, { pushUndo: false }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  // --- Toolbar actions -----------------------------------------------------

  const handleToggleMask = useCallback(() => {
    setMaskMode(!maskMode);
  }, [maskMode, setMaskMode]);

  const handleClearMask = useCallback(() => {
    canvasRef.current?.clearMask();
  }, []);

  // Region redraw: export mask at source dims, upload current image as source
  // and the mask, then run an inpaint job.
  const handleRedraw = useCallback(
    async (prompt: string) => {
      if (!currentAsset) return;
      const maskDataURL = canvasRef.current?.exportMask();
      if (!maskDataURL) {
        flash("Paint a region first.");
        return;
      }
      try {
        // Upload the current image as the inpaint source. Re-fetch the rendered
        // PNG so the source matches the displayed asset exactly.
        const srcRes = await fetch(assetFileUrl(currentAsset.id));
        const srcBlob = await srcRes.blob();
        const sourceAsset = await uploadFile(
          projectId,
          "source",
          srcBlob,
          "source.png",
        );
        const maskBlob = dataURLtoBlob(maskDataURL);
        const maskAsset = await uploadFile(
          projectId,
          "mask",
          maskBlob,
          "mask.png",
        );

        const spec = defaultGenSpec();
        spec.mode = "inpaint";
        spec.model = getImageModelForMode("inpaint");
        spec.prompt = prompt;
        spec.source_asset = sourceAsset.id;
        spec.mask_asset = maskAsset.id;
        spec.denoise = 0.85;
        spec.width = currentAsset.width || spec.width;
        spec.height = currentAsset.height || spec.height;

        await run(projectId, spec, {
          pushUndo: true,
          onDone: () => {
            canvasRef.current?.clearMask();
            setMaskMode(false);
          },
          onError: (m) => flash(m),
        });
      } catch (e) {
        flash((e as Error)?.message ?? "Redraw failed.");
      }
    },
    [currentAsset, projectId, run, setMaskMode, flash, getImageModelForMode],
  );

  // Text edit: upload current image as source, run an edit job.
  const handleTextEdit = useCallback(
    async (prompt: string) => {
      if (!currentAsset) return;
      try {
        const srcRes = await fetch(assetFileUrl(currentAsset.id));
        const srcBlob = await srcRes.blob();
        const sourceAsset = await uploadFile(
          projectId,
          "source",
          srcBlob,
          "source.png",
        );
        const spec = defaultGenSpec();
        spec.mode = "edit";
        spec.model = getImageModelForMode("edit");
        spec.prompt = prompt;
        spec.source_asset = sourceAsset.id;
        spec.width = currentAsset.width || spec.width;
        spec.height = currentAsset.height || spec.height;
        await run(projectId, spec, {
          pushUndo: true,
          onError: (m) => flash(m),
        });
      } catch (e) {
        flash((e as Error)?.message ?? "Edit failed.");
      }
    },
    [currentAsset, projectId, run, flash, getImageModelForMode],
  );

  const handleUpscale = useCallback(async () => {
    if (!currentAsset) return;
    try {
      const asset = await upscaleAsset(currentAsset.id);
      setCurrentAsset(asset, true);
    } catch (e) {
      flash((e as Error)?.message ?? "Upscale failed.");
    }
  }, [currentAsset, setCurrentAsset, flash]);

  const handleWhiteBg = useCallback(async () => {
    if (!currentAsset) return;
    try {
      const asset = await whitebgAsset(currentAsset.id);
      setCurrentAsset(asset, true);
    } catch (e) {
      flash((e as Error)?.message ?? "White BG failed.");
    }
  }, [currentAsset, setCurrentAsset, flash]);

  const handleExport = useCallback(
    async (fmt: ExportFormat) => {
      if (!currentAsset) return;
      try {
        const res = await fetch(assetExportUrl(currentAsset.id, fmt));
        if (!res.ok) throw new Error(`Export failed (${res.status})`);
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${project?.title || "figment"}-${currentAsset.id}.${fmt}`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      } catch (e) {
        flash((e as Error)?.message ?? "Export failed.");
      }
    },
    [currentAsset, project, flash],
  );

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-bg">
      {/* Left: Chat */}
      <aside className="flex w-[360px] shrink-0 flex-col border-r border-line bg-panel">
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <Link
            href="/"
            className="text-sm font-medium text-muted hover:text-ink"
          >
            ← Home
          </Link>
          <span className="max-w-[200px] truncate text-sm font-semibold text-ink">
            {project?.title ?? "…"}
          </span>
        </div>
        <div className="min-h-0 flex-1">
          <ChatPanel projectId={projectId} onRedraw={handleRedraw} />
        </div>
      </aside>

      {/* Center: Toolbar + Canvas + History */}
      <main className="flex min-w-0 flex-1 flex-col">
        <EditToolbar
          onToggleMask={handleToggleMask}
          onClearMask={handleClearMask}
          onTextEdit={handleTextEdit}
          onUpscale={handleUpscale}
          onWhiteBg={handleWhiteBg}
          onAddRef={() => setRefOpen(true)}
          onExport={handleExport}
        />

        <div className="relative min-h-0 flex-1 bg-zinc-50 p-4">
          <CanvasStage ref={canvasRef} />
        </div>

        <HistoryStrip projectId={projectId} />
      </main>

      {refOpen && (
        <ReferencePanel
          projectId={projectId}
          onClose={() => setRefOpen(false)}
        />
      )}

      {toast && (
        <div className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-xl bg-ink px-4 py-2 text-sm text-white shadow-soft">
          {toast}
        </div>
      )}
    </div>
  );
}

export default function EditorPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-screen w-screen items-center justify-center text-sm text-muted">
          Loading…
        </div>
      }
    >
      <EditorPageInner />
    </Suspense>
  );
}
