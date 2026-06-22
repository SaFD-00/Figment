#!/usr/bin/env bash
# Disk-budget guard. Source this and call `diskguard <gb_needed>` before large downloads.
# Aborts if the projected free space on ~ would drop below MIN_FREE_GB.

MIN_FREE_GB="${MIN_FREE_GB:-15}"

free_gb() {
  # Free GB on the volume that actually holds the downloads (AISTUDIO_HOME, which is normally a
  # symlink to /data) — NOT the small root volume. Portable across Linux/macOS via POSIX `df -Pk`.
  local target="${AISTUDIO_HOME:-$HOME}"
  [ -e "$target" ] || target="$HOME"
  df -Pk "$target" | awk 'NR==2 {print int($4/1048576)}'
}

diskguard() {
  local need_gb="${1:-0}"
  # Round decimal GB up to a whole number so the integer math below tolerates 0.25, 9.2, etc.
  need_gb="$(awk -v n="$need_gb" 'BEGIN{ printf "%d", (n>int(n) ? int(n)+1 : int(n)) }')"
  local free; free="$(free_gb)"
  local projected=$(( free - need_gb ))
  if (( projected < MIN_FREE_GB )); then
    echo "❌ diskguard: need ${need_gb}GB, only ${free}GB free; projected ${projected}GB < ${MIN_FREE_GB}GB floor. Aborting." >&2
    return 1
  fi
  echo "✓ diskguard: ${free}GB free, ${need_gb}GB needed, ${projected}GB projected (floor ${MIN_FREE_GB}GB)."
  return 0
}
