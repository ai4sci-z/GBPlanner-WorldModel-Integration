#!/usr/bin/env bash
# Native-Ubuntu side: docker load the image tars exported from WSL.
# Usage: m0_import_images.sh <dir>   (dir = mounted NTFS path or portable SSD,
#        e.g. /mnt/win/CCproject/backups/images)
set -o pipefail
DIR=${1:?usage: m0_import_images.sh <images-dir>}

[ -f "$DIR/manifest.txt" ] && { echo "=== manifest ==="; cat "$DIR/manifest.txt"; }

for f in "$DIR"/*.tar; do
  echo "LOADING $(basename "$f") ($(du -h "$f" | cut -f1))"
  docker load -i "$f" || { echo "FAIL $f"; exit 1; }
done

echo "=== verify: loaded images vs manifest ==="
docker images --format '{{.Repository}}:{{.Tag}} {{.ID}}' | grep -E ':jazzy|gbplanner-ref|voxblox_ros2_deps' | sort
echo "IMPORT_DONE — 逐行对照上方 manifest,ID 应一致"
