#!/usr/bin/env bash
# Optional machine-specific WSL demo disk; never formats an existing image.
set -euo pipefail
image=/mnt/d/AI/inse691-langfuse/minio.ext4
target=/mnt/inse691-langfuse-minio
mkdir -p /mnt/d/AI/inse691-langfuse "$target"
if [[ ! -e "$image" ]]; then
  (set -o noclobber; : > "$image")
  truncate -s 20G "$image"
  mkfs.ext4 -q "$image"
fi
if ! mountpoint -q "$target"; then mount -o loop "$image" "$target"; fi
chmod 0777 "$target"
# WSL may isolate shell mounts from systemd's Docker mount namespace.
pid="$(pgrep -x dockerd || true)"
if [[ -n "$pid" ]] && ! nsenter -t "$pid" -m -- mountpoint -q "$target"; then
  device="$(findmnt -n -o SOURCE -M "$target")"
  nsenter -t "$pid" -m -- mount "$device" "$target"
fi
df -h "$target"
