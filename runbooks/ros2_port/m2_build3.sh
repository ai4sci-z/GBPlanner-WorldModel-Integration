#!/usr/bin/env bash
# M2 slice 3: build after NTNU dev/noetic tsdf_integrator behavior patch
# (3 weighting Config fields + sparsity removal + fast-integrator abort
# criterion + ros_params alignment) and run the ported integrator gtest.
SRC=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/ros2_port/src/voxblox_ros2_minimal
echo "=== source: repo vendored copy (post ntnu patch) ==="

docker run --rm -v "$SRC":/src:ro voxblox_ros2_deps:jazzy bash -c '
  set -e
  source /opt/ros/jazzy/setup.bash
  mkdir -p /ws/src
  cp -r /src /ws/src/voxblox_ros2_minimal
  cd /ws
  export MAKEFLAGS=-j8
  echo "=== colcon build minimal set (up-to voxblox_ros, tests on) ==="
  colcon build --merge-install --executor sequential \
    --packages-up-to voxblox_ros \
    --cmake-args -DCMAKE_BUILD_TYPE=Release 2>&1 | tail -6
  RC=${PIPESTATUS[0]}
  echo "COLCON_RC=$RC"
  [ "$RC" -ne 0 ] && exit "$RC"
  echo "=== gtest: test_sdf_integrators (ntnu-ported thresholds) ==="
  ./build/voxblox/test_sdf_integrators 2>&1 | tail -25
  echo "GTEST_RC=${PIPESTATUS[0]}"
  echo "=== grep: no sparsity symbol must survive outside comments ==="
  grep -rn "sparsity" /ws/src/voxblox_ros2_minimal/voxblox/include /ws/src/voxblox_ros2_minimal/voxblox/src /ws/src/voxblox_ros2_minimal/voxblox_ros/include 2>/dev/null || echo "OK: no sparsity references left"
'
echo "DOCKER_RC=$?"
echo "=== DONE ==="
