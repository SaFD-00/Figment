#!/usr/bin/env bash
# Disk-budget guard. Source this and call `diskguard <gb_needed>` before large downloads.
# Aborts if the projected free space on ~ would drop below MIN_FREE_GB.

MIN_FREE_GB="${MIN_FREE_GB:-15}"

free_gb() {
  # Free GB on the volume that holds $HOME
  df -g "$HOME" | awk 'NR==2 {print $4}'
}

diskguard() {
  local need_gb="${1:-0}"
  local free; free="$(free_gb)"
  local projected=$(( free - need_gb ))
  if (( projected < MIN_FREE_GB )); then
    echo "❌ diskguard: need ${need_gb}GB, only ${free}GB free; projected ${projected}GB < ${MIN_FREE_GB}GB floor. Aborting." >&2
    return 1
  fi
  echo "✓ diskguard: ${free}GB free, ${need_gb}GB needed, ${projected}GB projected (floor ${MIN_FREE_GB}GB)."
  return 0
}
