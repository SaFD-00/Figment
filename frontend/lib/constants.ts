// Shared runtime constants mirroring backend contracts.

// Max reference images per request. Mirror of backend genspec.MAX_REFERENCE_IMAGES — keep in sync.
export const MAX_REFERENCE_IMAGES = 6;

// Local reference cap: on H100 the multi-ref local builders (Redux style, Kontext edit) consume
// every reference, so local matches the cloud cap; single-ref builders (identity, ControlNet) just
// use the first. Mirror of backend genspec.LOCAL_MAX_REFS — keep in sync.
export const LOCAL_MAX_REFERENCE_IMAGES = MAX_REFERENCE_IMAGES;

// Reference-image cap for the selected model. Local and cloud both top out at MAX_REFERENCE_IMAGES;
// builders that only need one reference take the first. Structural-typed param to avoid a circular
// import on Model.
export function refCap(model: { engine: string } | null | undefined): number {
  return model?.engine === "local-comfy" ? LOCAL_MAX_REFERENCE_IMAGES : MAX_REFERENCE_IMAGES;
}
