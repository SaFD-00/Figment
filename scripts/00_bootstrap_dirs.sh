#!/usr/bin/env bash
# Create the runtime home <repo>/AIStudio (models, ComfyUI, DB, logs, outputs all live here).
# Per AGENTS.md, large runtime artifacts belong on the /data volume, not the root volume. When
# AISTUDIO_HOME is unset and /data/<user>/Figment exists, we keep <repo>/AIStudio as a SYMLINK into
# /data so code paths stay identical while bytes land on /data (and stay git-ignored).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AISTUDIO_HOME="${AISTUDIO_HOME:-$REPO_ROOT/AIStudio}"

# Auto-symlink <repo>/AIStudio → /data/<user>/Figment/AIStudio on a fresh machine (idempotent).
DATA_HOME="/data/${USER}/Figment/AIStudio"
if [ "$AISTUDIO_HOME" = "$REPO_ROOT/AIStudio" ] && [ ! -e "$REPO_ROOT/AIStudio" ] && [ -d "/data/${USER}" ]; then
  mkdir -p "$DATA_HOME"
  ln -s "$DATA_HOME" "$REPO_ROOT/AIStudio"
  echo "↪ symlinked $REPO_ROOT/AIStudio → $DATA_HOME (AGENTS.md storage rule)"
fi

case "$AISTUDIO_HOME" in
  *CloudStorage*|*GoogleDrive*|*Dropbox*|*OneDrive*|*"Library/Mobile Documents"*)
    echo "ℹ AISTUDIO_HOME ($AISTUDIO_HOME) is inside a cloud-sync folder (by design)."
    echo "  Drive will sync the model weights + SQLite DB. If churn/lock issues appear,"
    echo "  exclude this folder from Drive sync or point AISTUDIO_HOME elsewhere in .env."
    ;;
esac

echo "Bootstrapping $AISTUDIO_HOME ..."
mkdir -p "$AISTUDIO_HOME"/{comfyui,outputs,logs}
mkdir -p "$AISTUDIO_HOME"/models/{checkpoints,unet,clip,clip_vision,vae,loras,controlnet,upscale_models,style_models,pulid,instantid,ipadapter,video}

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
  upscale_models: upscale_models
  style_models: style_models
  pulid: pulid
  instantid: instantid
  ipadapter: ipadapter
  video: video
YAML

echo "✓ Created:"
find "$AISTUDIO_HOME" -maxdepth 2 -type d | sort
echo "✓ extra_model_paths.yaml written to $AISTUDIO_HOME/extra_model_paths.yaml"
