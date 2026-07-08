#!/usr/bin/env bash
# M2 slice 2: rebuild from the REPO vendored copy (canonical fork) after
# maintenance patches: ghost rviz_plugin dep removed; node mains fixed
# (rclcpp::init before gflags + automatically_declare_parameters_from_overrides).
# New acceptance: (a) --packages-up-to voxblox_ros no longer drags rviz_plugin,
# (b) -p world_frame:=map actually lands in the node (param readable back).
SRC=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/ros2_port/src/voxblox_ros2_minimal
echo "=== source: repo vendored copy ==="

docker run --rm -v "$SRC":/src:ro voxblox_ros2_deps:jazzy bash -c '
  set -e
  source /opt/ros/jazzy/setup.bash
  mkdir -p /ws/src
  cp -r /src /ws/src/voxblox_ros2_minimal
  cd /ws
  echo "=== minimal set check: packages-up-to voxblox_ros (expect 7, NO rviz_plugin) ==="
  colcon list --packages-up-to voxblox_ros --names-only
  export MAKEFLAGS=-j8
  echo "=== full colcon build (9 pkgs, merge-install, Release) ==="
  colcon build --merge-install --executor sequential \
    --cmake-args -DCMAKE_BUILD_TYPE=Release 2>&1 | tail -6
  RC=${PIPESTATUS[0]}
  echo "COLCON_RC=$RC"
  [ "$RC" -ne 0 ] && exit "$RC"
  source install/setup.bash
  echo "=== param plumbing E2E: esdf_server -p world_frame:=map ==="
  timeout 10 install/lib/voxblox_ros/esdf_server --ros-args -p world_frame:=map > /tmp/esdf.log 2>&1 &
  sleep 4
  echo -n "param world_frame readback: "
  ros2 param get /voxblox world_frame 2>&1 | tail -1
  wait || true
  grep -ci "deprecated" /tmp/esdf.log >/dev/null && echo "WARN: deprecated remap warning still present" || echo "OK: no deprecated-remap warning"
  echo "=== launch/cfg installed to share (INSTALL_TO_SHARE) ==="
  ls install/share/voxblox_ros/ | head -8
'
echo "DOCKER_RC=$?"
echo "=== DONE ==="
