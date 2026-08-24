#!/usr/bin/env bash
# Build the exact ROS 2 runtime consumed by m5_direct_run.sh and reject stale
# binaries before replacing the gbplanner_stack:jazzy tag.
set -euo pipefail

FEAT_ROOT="${FEAT_ROOT:-$(git rev-parse --show-toplevel)}"
IMAGE="${IMAGE:-gbplanner_stack:jazzy}"
BASE_IMAGE="voxblox_ros2_deps:jazzy"
BASE_ID="sha256:5f4a1875a8626aec838ecd51d4844bf4147f743cb981e872f166a8d365a01fca"
FEAT_COMMIT="$(git -C "$FEAT_ROOT" rev-parse HEAD)"

ACTUAL_BASE_ID="$(docker image inspect voxblox_ros2_deps:jazzy --format '{{.Id}}')"
if [ "$ACTUAL_BASE_ID" != "$BASE_ID" ]; then
  echo "base image drift: expected $BASE_ID, got $ACTUAL_BASE_ID" >&2
  exit 3
fi

docker build --network=host \
  --pull=false \
  --build-arg "BASE_IMAGE=$BASE_IMAGE" \
  --build-arg "FEAT_COMMIT=$FEAT_COMMIT" \
  --file "$FEAT_ROOT/runbooks/ros2_port/m5_stack.Dockerfile" \
  --tag "$IMAGE" \
  "$FEAT_ROOT/ros2_port"

IMAGE_ID="$(docker image inspect "$IMAGE" --format '{{.Id}}')"
IMAGE_REVISION="$(docker image inspect "$IMAGE" \
  --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')"
if [ "$IMAGE_REVISION" != "$FEAT_COMMIT" ]; then
  echo "runtime image revision mismatch: expected $FEAT_COMMIT, got $IMAGE_REVISION" >&2
  exit 4
fi

docker run --rm "$IMAGE" bash -lc '
  set -e
  source /opt/ros/jazzy/setup.bash
  source /ws/install/setup.bash
  ros2 pkg executables gbplanner_node | grep -F "gbplanner_node pci_trigger_node"
  strings /ws/install/lib/gbplanner_node/pci_trigger_node | grep -F "wait_for_enable"
  strings /ws/install/lib/gbplanner_node/pci_trigger_node | grep -F "first non-empty path published; trigger timer stopped"
'

printf 'STACK_IMAGE=%s\nSTACK_IMAGE_ID=%s\nFEAT_COMMIT=%s\nBASE_IMAGE_ID=%s\n' \
  "$IMAGE" "$IMAGE_ID" "$FEAT_COMMIT" "$BASE_ID"
