#!/usr/bin/env bash
# Rebuild and test the current ROS 2 GBPlanner source in its pinned Jazzy build image.
# navlab/official-baseline is a runtime image and intentionally lacks pcl_ros headers.
set -eo pipefail

FEAT_ROOT="${FEAT_ROOT:-/home/ai4s/projects/gbp-feat}"
IMAGE="${IMAGE:-voxblox_ros2_deps:jazzy}"
RUN_SMOKE=1

if [ "${1:-}" = "--build-only" ]; then
  RUN_SMOKE=0
elif [ -n "${1:-}" ]; then
  echo "usage: $0 [--build-only]" >&2
  exit 2
fi

SOURCE_ROOT="$FEAT_ROOT/ros2_port/src"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVIDENCE_ROOT="${EVIDENCE_ROOT:-/home/ai4s/aa_runs/gbplanner_verify/$STAMP}"
mkdir -p "$EVIDENCE_ROOT"

python3 -m pytest -q \
  "$FEAT_ROOT/ros2_port/adapter/test_intent_z.py" \
  "$FEAT_ROOT/ros2_port/wm_mapping/test_enable_lease.py" \
  "$FEAT_ROOT/ros2_port/wm_mapping/test_planning_frame.py" \
  "$FEAT_ROOT/runbooks/ros2_port/test_validate_m5_run.py"

echo "FEAT_HEAD=$(git -C "$FEAT_ROOT" rev-parse HEAD)"
echo "IMAGE=$IMAGE"
echo "EVIDENCE_ROOT=$EVIDENCE_ROOT"
docker image inspect "$IMAGE" --format 'IMAGE_ID={{.Id}} CREATED={{.Created}}'

docker run --rm "$IMAGE" \
  test -f /opt/ros/jazzy/include/pcl_ros/pcl_ros/transforms.hpp

set +e
docker run --rm \
  -e "RUN_SMOKE=$RUN_SMOKE" \
  -v "$SOURCE_ROOT":/source:ro \
  "$IMAGE" bash -lc '
    set -eo pipefail
    source /opt/ros/jazzy/setup.bash
    mkdir -p /work/src
    cp -a /source/. /work/src/
    cd /work
    export MAKEFLAGS=-j4

    colcon build --merge-install --executor sequential \
      --packages-up-to gbplanner_node \
      --event-handlers console_cohesion+ \
      --cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo

    source /work/install/setup.bash
    colcon test --merge-install --packages-select gbplanner_core gbplanner_node \
      --event-handlers console_cohesion+
    colcon test-result --test-result-base /work/build --verbose
    ros2 pkg executables gbplanner_node

    if [ "$RUN_SMOKE" = "1" ]; then
      /work/install/lib/gbplanner_node/gbplanner_node --ros-args \
        --params-file /source/gbplanner_node/config/sim_gbplanner.yaml \
        >/tmp/gbplanner_node.log 2>&1 &
      gbp_pid=$!
      sleep 4
      /work/install/lib/gbplanner_node/pci_trigger_node --ros-args \
        -p trigger_period_sec:=3.0 -p frame_id:=world \
        >/tmp/pci_trigger.log 2>&1 &
      pci_pid=$!

      set +e
      python3 /source/gbplanner_node/test/m4_feeder.py 60
      smoke_rc=$?
      set -e
      tail -20 /tmp/gbplanner_node.log
      tail -10 /tmp/pci_trigger.log
      kill "$gbp_pid" "$pci_pid" 2>/dev/null || true
      wait "$gbp_pid" "$pci_pid" 2>/dev/null || true
      [ "$smoke_rc" -eq 0 ] || exit "$smoke_rc"
    fi
  ' 2>&1 | tee "$EVIDENCE_ROOT/verify.log"
rc=${PIPESTATUS[0]}
set -e

echo "VERIFY_RC=$rc" | tee "$EVIDENCE_ROOT/result.txt"
exit "$rc"
