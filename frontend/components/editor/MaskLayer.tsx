"use client";

// Presentational mask layer used by CanvasStage. Renders white brush strokes
// (eraser uses destination-out). The parent owns the stroke state and the
// layer ref (needed to export the mask at exact source dimensions).
//
// Points and stroke widths are in DISPLAY pixels (the stage's coordinate
// space). On export, exportMaskDataURL scales the whole layer up to source
// resolution uniformly via pixelRatio = sourceWidth / displayWidth.

import { forwardRef } from "react";
import { Layer, Line } from "react-konva";
import type Konva from "konva";

export interface Stroke {
  points: number[]; // display-px coordinates
  size: number; // brush diameter in display pixels
  eraser: boolean;
}

interface Props {
  strokes: Stroke[];
  visible: boolean;
}

export const MaskLayer = forwardRef<Konva.Layer, Props>(function MaskLayer(
  { strokes, visible },
  ref,
) {
  return (
    <Layer ref={ref} opacity={visible ? 0.5 : 0}>
      {strokes.map((stroke, i) => (
        <Line
          key={i}
          points={stroke.points}
          stroke="#ffffff"
          strokeWidth={stroke.size}
          lineCap="round"
          lineJoin="round"
          tension={0.3}
          globalCompositeOperation={
            stroke.eraser ? "destination-out" : "source-over"
          }
        />
      ))}
    </Layer>
  );
});
