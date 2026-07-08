#!/usr/bin/env bash
# Migration: docker save all jazzy-line images (+oracle+deps) to the shared
# NTFS partition so native Ubuntu can docker load them (dual-boot same disk).
# Resumable: skips files that already exist and are non-empty.
export PATH=/usr/local/go/bin:/usr/bin:/bin
OUT=/mnt/c/CCproject/backups/images
mkdir -p "$OUT"

IMAGES=$(docker images --format '{{.Repository}}:{{.Tag}}' | grep -E ':jazzy|gbplanner-ref|voxblox_ros2_deps')
echo "=== export list ==="; echo "$IMAGES"

for img in $IMAGES; do
  f="$OUT/$(echo "$img" | tr '/:' '__').tar"
  if [ -s "$f" ]; then echo "SKIP(exists) $img"; continue; fi
  echo "SAVING $img"
  if docker save "$img" -o "$f"; then
    echo "OK $img -> $(du -h "$f" | cut -f1)"
  else
    echo "FAIL $img"; rm -f "$f"
  fi
done

docker images --format '{{.Repository}}:{{.Tag}} {{.ID}}' \
  | grep -E ':jazzy|gbplanner-ref|voxblox_ros2_deps' > "$OUT/manifest.txt"
echo "=== final ==="
ls -lh "$OUT" | tail -20
echo EXPORT_DONE
