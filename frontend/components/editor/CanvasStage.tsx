"use client";

// react-konva canvas. Must be a client component and is dynamically imported
// with { ssr: false } by the parent (Konva touches `window`).
//
// Layout:
//   - Layer 0: the current image (Konva.Image loaded via window.Image).
//   - Layer 1: the mask brush strokes (MaskLayer) — white lines / eraser.
//
// The stage is fit to its container while preserving aspect ratio. We track
// scale = displayWidth / sourceWidth so the mask can be exported at EXACTLY
// source dimensions later. Stroke sizes are stored in SOURCE pixels.

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { Stage, Layer, Image as KonvaImage } from "react-konva";
import type Konva from "konva";
import { assetFileUrl } from "../../lib/api";
import { fitContain, exportMaskDataURL } from "../../lib/canvas";
import { useEditorStore } from "../../lib/store";
import { ProgressOverlay } from "./ProgressOverlay";
import { MaskLayer, type Stroke } from "./MaskLayer";

export interface CanvasStageHandle {
  // Export the mask at exact source dimensions (PNG data URL), or null if empty.
  exportMask: () => string | null;
  clearMask: () => void;
  hasMaskStrokes: () => boolean;
}

export const CanvasStage = forwardRef<CanvasStageHandle>(
  function CanvasStage(_props, ref) {
    const containerRef = useRef<HTMLDivElement>(null);
    const maskLayerRef = useRef<Konva.Layer>(null);
    const [box, setBox] = useState({ w: 0, h: 0 });
    const [img, setImg] = useState<HTMLImageElement | null>(null);
    const [natural, setNatural] = useState({ w: 0, h: 0 });
    const [strokes, setStrokes] = useState<Stroke[]>([]);
    const drawing = useRef(false);

    const currentAsset = useEditorStore((s) => s.currentAsset);
    const maskMode = useEditorStore((s) => s.maskMode);
    const brushSize = useEditorStore((s) => s.brushSize);
    const eraser = useEditorStore((s) => s.eraser);
    const initialPrompt = useEditorStore((s) => s.initialPrompt);

    // The originating prompt, pinned to the left of the canvas while you chat/edit.
    const promptCard = initialPrompt ? (
      <div className="pointer-events-auto absolute left-3 top-3 z-20 max-w-[260px] rounded-lg border border-line bg-panel/90 px-3 py-2 shadow-soft">
        <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted">
          원본 프롬프트
        </div>
        <p className="max-h-32 overflow-y-auto whitespace-pre-wrap break-words text-xs leading-snug text-ink">
          {initialPrompt}
        </p>
      </div>
    ) : null;

    // Observe container size for responsive fit.
    useLayoutEffect(() => {
      const el = containerRef.current;
      if (!el) return;
      const update = () => setBox({ w: el.clientWidth, h: el.clientHeight });
      update();
      const ro = new ResizeObserver(update);
      ro.observe(el);
      return () => ro.disconnect();
    }, []);

    // Load the current asset image via window.Image (Konva needs a real image).
    useEffect(() => {
      if (!currentAsset) {
        setImg(null);
        return;
      }
      const image = new window.Image();
      image.crossOrigin = "anonymous";
      image.src = assetFileUrl(currentAsset.id);
      let alive = true;
      image.onload = () => {
        if (!alive) return;
        setImg(image);
        setNatural({
          w: currentAsset.width || image.naturalWidth,
          h: currentAsset.height || image.naturalHeight,
        });
      };
      return () => {
        alive = false;
      };
    }, [currentAsset]);

    // Clear strokes whenever the underlying image changes.
    useEffect(() => {
      setStrokes([]);
    }, [currentAsset?.id]);

    const srcW = natural.w || 1;
    const srcH = natural.h || 1;
    const fit = fitContain(srcW, srcH, box.w, box.h);
    const displayW = fit.width;
    const displayH = fit.height;

    useImperativeHandle(
      ref,
      () => ({
        exportMask: () => {
          if (!maskLayerRef.current || strokes.length === 0) return null;
          return exportMaskDataURL(
            maskLayerRef.current,
            srcW,
            srcH,
            displayW || 1,
          );
        },
        clearMask: () => setStrokes([]),
        hasMaskStrokes: () => strokes.length > 0,
      }),
      [strokes, srcW, srcH, displayW],
    );

    function pointerSourcePos(
      stage: Konva.Stage | null,
    ): { x: number; y: number } | null {
      if (!stage) return null;
      const p = stage.getPointerPosition();
      return p ? { x: p.x, y: p.y } : null;
    }

    function handleDown(e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) {
      if (!maskMode) return;
      drawing.current = true;
      const pos = pointerSourcePos(e.target.getStage());
      if (!pos) return;
      setStrokes((s) => [
        ...s,
        { points: [pos.x, pos.y], size: brushSize, eraser },
      ]);
    }

    function handleMove(e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) {
      if (!maskMode || !drawing.current) return;
      const pos = pointerSourcePos(e.target.getStage());
      if (!pos) return;
      setStrokes((s) => {
        if (s.length === 0) return s;
        const last = s[s.length - 1];
        const updated: Stroke = {
          ...last,
          points: [...last.points, pos.x, pos.y],
        };
        return [...s.slice(0, -1), updated];
      });
    }

    function handleUp() {
      drawing.current = false;
    }

    if (!currentAsset) {
      return (
        <div
          ref={containerRef}
          className="relative flex h-full w-full items-center justify-center text-sm text-muted"
        >
          {promptCard}
          No image yet — generate one to begin.
        </div>
      );
    }

    return (
      <div
        ref={containerRef}
        className="relative flex h-full w-full items-center justify-center overflow-hidden"
      >
        {promptCard}
        {displayW > 0 && displayH > 0 && img && (
          <div
            className="relative shadow-soft"
            style={{ width: displayW, height: displayH }}
          >
            <Stage
              width={displayW}
              height={displayH}
              onMouseDown={handleDown}
              onMouseMove={handleMove}
              onMouseUp={handleUp}
              onMouseLeave={handleUp}
              onTouchStart={handleDown}
              onTouchMove={handleMove}
              onTouchEnd={handleUp}
              style={{ cursor: maskMode ? "crosshair" : "default" }}
            >
              <Layer listening={false}>
                <KonvaImage image={img} width={displayW} height={displayH} />
              </Layer>
              <MaskLayer
                ref={maskLayerRef}
                strokes={strokes}
                visible={maskMode}
              />
            </Stage>

            <ProgressOverlay />
          </div>
        )}
      </div>
    );
  },
);
