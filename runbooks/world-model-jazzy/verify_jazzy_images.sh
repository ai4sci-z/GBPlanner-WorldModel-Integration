#!/usr/bin/env bash
# jazzy 镜像开箱验真:tag 存在≠内容是 jazzy。逐个进容器查 /opt/ros + 关键产物。
set -o pipefail
probe() { # probe <image> <cmd...>
  local img="$1"; shift
  echo "── ${img}"
  docker run --rm --entrypoint sh "$img" -c "$*" 2>&1 | sed 's/^/   /'
}
echo "=== 1. ros-base:jazzy(应只有 jazzy) ==="
probe navlab/ros-base:jazzy-latest 'ls /opt/ros/'
echo "=== 2. slam-cartographer:jazzy ==="
probe navlab/slam-cartographer:jazzy-latest 'ls /opt/ros/; ls /opt/ros/jazzy/share 2>/dev/null | grep -c cartographer && echo cartographer_pkgs_found'
echo "=== 3. gazebo-headless:jazzy(新建,查 gz + ROS) ==="
probe navlab/gazebo-headless:jazzy-latest 'ls /opt/ros/; gz sim --versions 2>/dev/null | head -1; ls /workspace 2>/dev/null'
echo "=== 4. fast-lio:jazzy(新建,查工作区真产物) ==="
probe navlab/fast-lio:jazzy-latest 'ls /opt/ros/; ls /workspace/ros_ws/install 2>/dev/null; test -f /usr/local/lib/liblivox_lidar_sdk_shared.so && echo livox_so_OK'
echo "=== 5. companion(同ID疑点!里面到底哪个 distro) ==="
probe navlab/companion:jazzy-09a5aa472901 'ls /opt/ros/ 2>/dev/null || echo no_/opt/ros'
echo "=== 6. ardupilot-sitl(预期 distro 无关) ==="
probe navlab/ardupilot-sitl:jazzy-latest 'ls /opt/ros/ 2>/dev/null || echo no_/opt/ros; ls /ardupilot 2>/dev/null | head -3; command -v arduplane arducopter sim_vehicle.py 2>/dev/null; ls / | head -20'
echo "=== 7. mavlink-router(预期 distro 无关) ==="
probe navlab/mavlink-router:jazzy-latest 'ls /opt/ros/ 2>/dev/null || echo no_/opt/ros; command -v mavlink-routerd && echo routerd_OK'
echo "=== DONE ==="
