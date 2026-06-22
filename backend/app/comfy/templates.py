"""Validate that the custom-node class_types our builders rely on are installed in ComfyUI.
Called at startup against /object_info so we fail fast with a clear message instead of an
opaque 400 from /prompt later.
"""
from __future__ import annotations

from app.comfy.client import ComfyUIClient

# Grouped by feature so the error message tells you which capability is unavailable.
REQUIRED_NODES: dict[str, list[str]] = {
    "core (txt2img/sdxl)": [
        "CheckpointLoaderSimple", "CLIPTextEncode", "EmptyLatentImage",
        "KSampler", "VAEDecode", "VAEEncode", "SaveImage", "LoadImage", "LoraLoader",
    ],
    # Chroma/Redux default to native CUDA loaders (fp8 safetensors); these are core ComfyUI.
    "chroma/flux native": ["UNETLoader", "CLIPLoader", "DualCLIPLoader", "VAELoader",
                           "EmptySD3LatentImage", "FluxGuidance"],
    "inpaint": ["VAEEncodeForInpaint", "ImageToMask", "InpaintModelConditioning"],
    "reference edit": ["ReferenceLatent"],
    "controlnet": ["ControlNetLoader", "ControlNetApplyAdvanced"],
    "redux style": ["StyleModelLoader", "CLIPVisionLoader", "CLIPVisionEncode"],
    "upscale": ["UpscaleModelLoader", "ImageUpscaleWithModel"],
}

# Nodes that are nice-to-have; a missing one disables one feature but shouldn't block startup.
# GGUF loaders are now optional (only flux-fill/kontext use them); identity/pose/video/USDU come
# from custom nodes (scripts/12_install_custom_nodes.sh) and degrade gracefully if absent.
OPTIONAL_NODES = {
    "UnetLoaderGGUF", "DualCLIPLoaderGGUF", "CLIPLoaderGGUF",
    "TextEncodeQwenImageEdit", "StyleModelApply",
    "CannyEdgePreprocessor", "DepthAnythingV2Preprocessor", "ScribblePreprocessor",
    "LineArtPreprocessor", "DWPreprocessor",
    # identity / face
    "InstantIDModelLoader", "InstantIDFaceAnalysis", "ApplyInstantID",
    "IPAdapterUnifiedLoaderFaceID", "IPAdapterFaceID",
    "PulidFluxModelLoader", "PulidFluxEvaClipLoader", "PulidFluxInsightFaceLoader", "ApplyPulidFlux",
    # upscale / video (Wan 2.2 nodes are native core, listed here only for startup visibility)
    "UltimateSDUpscale", "WanImageToVideo", "EmptyHunyuanLatentVideo",
    "Wan22ImageToVideoLatent", "KSamplerAdvanced", "LoraLoaderModelOnly", "SaveAnimatedWEBP",
}


async def validate_required_nodes(client: ComfyUIClient) -> dict:
    """Returns {'ok': bool, 'missing': {feature: [nodes]}, 'missing_optional': [nodes]}."""
    try:
        info = await client.object_info()
    except Exception as e:  # ComfyUI not up yet
        return {"ok": False, "error": f"could not reach ComfyUI /object_info: {e}", "missing": {}, "missing_optional": []}

    available = set(info.keys())
    missing: dict[str, list[str]] = {}
    for feature, nodes in REQUIRED_NODES.items():
        gone = [n for n in nodes if n not in available]
        if gone:
            missing[feature] = gone
    missing_optional = [n for n in OPTIONAL_NODES if n not in available]
    # Only "core" being present is required to boot; others degrade gracefully.
    core_ok = "core (txt2img/sdxl)" not in missing
    return {"ok": core_ok, "missing": missing, "missing_optional": missing_optional}
