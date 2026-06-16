// Shared runtime constants mirroring backend contracts.

// Max reference images per request. Mirror of backend genspec.MAX_REFERENCE_IMAGES — keep in sync.
export const MAX_REFERENCE_IMAGES = 6;

// Local qwen-edit multi-reference cap: the ComfyUI node TextEncodeQwenImageEditPlus exposes
// image1..image3 only. Mirror of backend genspec.LOCAL_QWEN_EDIT_MAX_REFS — keep in sync.
export const LOCAL_MAX_REFERENCE_IMAGES = 3;

// Reference-image cap for the selected model: local ComfyUI (qwen-edit) tops out at 3,
// cloud models take the full 6. Structural-typed param to avoid a circular import on Model.
export function refCap(model: { engine: string } | null | undefined): number {
  return model?.engine === "local-comfy" ? LOCAL_MAX_REFERENCE_IMAGES : MAX_REFERENCE_IMAGES;
}
