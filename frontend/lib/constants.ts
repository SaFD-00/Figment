// Shared runtime constants mirroring backend contracts.

// Max reference images per request. Mirror of backend genspec.MAX_REFERENCE_IMAGES — keep in sync.
export const MAX_REFERENCE_IMAGES = 6;

// Local reference cap: the local lineup uses IP-Adapter Plus, which conditions on a SINGLE
// reference image, so local reference tops out at 1. Mirror of backend genspec.LOCAL_MAX_REFS — keep in sync.
export const LOCAL_MAX_REFERENCE_IMAGES = 1;

// Reference-image cap for the selected model: local ComfyUI (IP-Adapter Plus) takes a single
// reference, cloud models take the full 6. Structural-typed param to avoid a circular import on Model.
export function refCap(model: { engine: string } | null | undefined): number {
  return model?.engine === "local-comfy" ? LOCAL_MAX_REFERENCE_IMAGES : MAX_REFERENCE_IMAGES;
}
