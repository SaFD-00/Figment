#!/usr/bin/env bash
# Create the runtime home <repo>/AIStudio (models, ComfyUI, DB, logs, outputs all live here).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AISTUDIO_HOME="${AISTUDIO_HOME:-$REPO_ROOT/AIStudio}"

case "$AISTUDIO_HOME" in
  *CloudStorage*|*GoogleDrive*|*Dropbox*|*OneDrive*|*"Library/Mobile Documents"*)
    echo "ℹ AISTUDIO_HOME ($AISTUDIO_HOME) is inside a cloud-sync folder (by design)."
    echo "  Drive will sync the model weights + SQLite DB. If churn/lock issues appear,"
    echo "  exclude this folder from Drive sync or point AISTUDIO_HOME elsewhere in .env."
    ;;
esac

echo "Bootstrapping $AISTUDIO_HOME ..."
mkdir -p "$AISTUDIO_HOME"/{comfyui,outputs,logs}
mkdir -p "$AISTUDIO_HOME"/models/{checkpoints,unet,clip,clip_vision,vae,loras,controlnet,ipadapter,upscale_models,style_models,pulid}

# extra_model_paths.yaml so ComfyUI reads weights from ~/AIStudio/models (single source of truth)
cat > "$AISTUDIO_HOME/extra_model_paths.yaml" <<YAML
imggen:
  base_path: $AISTUDIO_HOME/models
  checkpoints: checkpoints
  unet: unet
  clip: clip
  clip_vision: clip_vision
  vae: vae
  loras: loras
  controlnet: controlnet
  ipadapter: ipadapter
  upscale_models: upscale_models
  style_models: style_models
  pulid: pulid
YAML

echo "✓ Created:"
find "$AISTUDIO_HOME" -maxdepth 2 -type d | sort
echo "✓ extra_model_paths.yaml written to $AISTUDIO_HOME/extra_model_paths.yaml"
