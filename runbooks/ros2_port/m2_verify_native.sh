#!/usr/bin/env bash
# GATE-6: M2 复验(原生 Linux 版,HANDOVER_LINUX.md §4 GATE-6)
#   sg docker -c 'bash runbooks/ros2_port/m2_verify_native.sh'
#
# 移植自 m2_build3.sh(WSL 版),只做路径参数化;口径逐字不变。
# 验收: COLCON_RC=0 + test_sdf_integrators 10/10 PASSED + 无残留 sparsity 符号
# 前置: GATE-5 的 voxblox_ros2_deps:jazzy 镜像
# 铁律: voxblox 工作区禁 rosdep(package.xml 有 ROS1 时代 key 会炸),依赖走 m2_deps.Dockerfile 显式清单。
SRC="${SRC:-$(cd "$(dirname "$0")/../../ros2_port/src/voxblox_ros2_minimal" && pwd)}"
echo "=== source: ${SRC} (repo vendored copy, post ntnu patch) ==="
[ -d "$SRC" ] || { echo "SRC 不存在: $SRC"; exit 9; }

docker run --rm -v "$SRC":/src:ro voxblox_ros2_deps:jazzy bash -c '
  set -e
  source /opt/ros/jazzy/setup.bash
  mkdir -p /ws/src
  cp -r /src /ws/src/voxblox_ros2_minimal
  cd /ws
  export MAKEFLAGS=-j"$(nproc)"
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
