// Canvas / mask export helpers.
//
// IMPORTANT: The exported mask dimensions MUST equal the SOURCE image
// dimensions (sourceWidth x sourceHeight). The backend asserts that the mask
// and source share identical width/height — a mismatch is a hard error.
//
// The mask layer is rendered on screen at `displayWidth` (scaled down to fit
// the stage). We render it back up to native source resolution using a
// pixelRatio of sourceWidth / displayWidth, then composite the painted strokes
// (white) onto a solid black background so unpainted regions are pure black.

import type Konva from "konva";

type LayerLike = Pick<Konva.Layer, "toCanvas">;

/**
 * Export the painted mask as a PNG data URL sized EXACTLY
 * sourceWidth x sourceHeight. Painted pixels -> white (255), unpainted -> black (0).
 */
export function exportMaskDataURL(
  maskLayer: LayerLike,
  sourceWidth: number,
  sourceHeight: number,
  displayWidth: number,
): string {
  // Scale factor to bring the on-screen layer back up to native resolution.
  const pixelRatio = sourceWidth / displayWidth;

  // Render the mask layer (transparent bg + white strokes) at native res.
  const painted = maskLayer.toCanvas({ pixelRatio });

  // Composite onto a solid black canvas at exact source dimensions.
  const out = document.createElement("canvas");
  out.width = sourceWidth;
  out.height = sourceHeight;
  const ctx = out.getContext("2d");
  if (!ctx) {
    throw new Error("Could not acquire 2d context for mask export");
  }

  // Black background = unpainted region.
  ctx.fillStyle = "#000000";
  ctx.fillRect(0, 0, sourceWidth, sourceHeight);

  // Draw the painted (white) strokes on top. The Konva canvas may differ by a
  // sub-pixel from exact source dims due to rounding of pixelRatio, so we
  // force-scale it into the exact target rect.
  ctx.drawImage(painted, 0, 0, sourceWidth, sourceHeight);

  return out.toDataURL("image/png");
}

/** Convert a data URL (e.g. from canvas.toDataURL) into a Blob for upload. */
export function dataURLtoBlob(dataURL: string): Blob {
  const [header, base64] = dataURL.split(",");
  const mimeMatch = /data:([^;]+);base64/.exec(header);
  const mime = mimeMatch ? mimeMatch[1] : "image/png";
  const binary = atob(base64);
  const len = binary.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return new Blob([bytes], { type: mime });
}

/**
 * Compute a contained fit (preserve aspect ratio) of a source image inside a
 * bounding box. Returns the display width/height and the uniform scale.
 */
export function fitContain(
  srcW: number,
  srcH: number,
  boxW: number,
  boxH: number,
): { width: number; height: number; scale: number } {
  if (srcW <= 0 || srcH <= 0 || boxW <= 0 || boxH <= 0) {
    return { width: 0, height: 0, scale: 1 };
  }
  const scale = Math.min(boxW / srcW, boxH / srcH);
  return {
    width: Math.round(srcW * scale),
    height: Math.round(srcH * scale),
    scale,
  };
}
