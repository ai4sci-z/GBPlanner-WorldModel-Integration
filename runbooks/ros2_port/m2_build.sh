#!/usr/bin/env bash
# M2 slice 1: colcon build PRISTINE snt-arg/voxblox_ros2_minimal (d08e9d4) on Jazzy.
# Deps image = voxblox_ros2_deps:jazzy (recipe mirrored from GabrieleSantangelo
# voxblox-ros2 Dockerfile.base @243dc3e, the Jazzy-CI-proven combo).
# Source mounted read-only; copied to container-native FS before build.
# Discipline: NO source patches in this slice (ntnu tsdf_integrator patch and
# Gabriele node fixes come as separate later slices) - isolates recipe vs code.
SRC=/home/ai4s/ros2_port_ws/src/voxblox_ros2_minimal
echo "=== base HEAD ==="
git -C "$SRC" log --oneline -1

docker run --rm -v "$SRC":/src:ro voxblox_ros2_deps:jazzy bash -c '
  set -e
  source /opt/ros/jazzy/setup.bash
  mkdir -p /ws/src
  cp -r /src /ws/src/voxblox_ros2_minimal
  cd /ws
  export MAKEFLAGS=-j8
  echo "=== colcon build (merge-install, Release) ==="
  colcon build --merge-install --executor sequential \
    --event-handlers console_cohesion+ \
    --cmake-args -DCMAKE_BUILD_TYPE=Release 2>&1 | tail -40
  RC=${PIPESTATUS[0]}
  echo "COLCON_RC=$RC"
  [ "$RC" -ne 0 ] && exit "$RC"
  source install/setup.bash
  echo "=== packages built ==="
  ros2 pkg list 2>/dev/null | grep -E "voxblox|minkindr|eigen_check|xmlrpc"
  echo "=== voxblox_ros executables ==="
  ls install/lib/voxblox_ros/ 2>/dev/null
  echo "=== voxblox_msgs interfaces ==="
  ros2 interface list 2>/dev/null | grep voxblox | head -10
  echo "=== esdf_server smoke (3s, expect param/topic init then timeout-kill) ==="
  timeout 3 install/lib/voxblox_ros/esdf_server --ros-args -p world_frame:=map 2>&1 | head -8 || true
  echo "SMOKE_DONE"
'
echo "DOCKER_RC=$?"
echo "=== DONE ==="
