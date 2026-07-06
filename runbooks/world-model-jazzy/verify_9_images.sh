#!/usr/bin/env bash
# 逐个开箱验 9 个 jazzy 镜像的内部真货。不看存在,看内容是否完整、是否真 jazzy。
set +e
chk() {
  local img="$1"; shift
  echo "────────── $img"
  docker run --rm --entrypoint bash "$img" -c "$*" 2>&1 | sed 's/^/   /' | head -6
}
chk navlab/ros-base:jazzy-latest 'grep VERSION= /etc/os-release; echo -n "ros: "; ls /opt/ros'
chk navlab/official-baseline:jazzy-latest 'echo -n "ros: "; ls /opt/ros; echo -n "arducopter bin: "; find / -name arducopter -type f 2>/dev/null | head -1; echo -n "ardupilot pkgs: "; ls /opt/navlab_official_ws/install 2>/dev/null | grep -cE "ardupilot|gz"; echo -n "maze world: "; find / -name "*.sdf" -path "*maze*" 2>/dev/null | head -1'
chk navlab/gazebo-headless:jazzy-latest 'echo -n "ros: "; ls /opt/ros; echo -n "gz: "; which gz; gz sim --versions 2>/dev/null | head -1'
chk navlab/slam-cartographer:jazzy-latest 'echo -n "ros: "; ls /opt/ros; echo -n "cartographer node: "; find /opt/ros -name cartographer_node 2>/dev/null | head -1; echo -n "navlab pkgs: "; ls /opt/navlab_ws/install 2>/dev/null | wc -l'
chk navlab/gazebo-sensor:jazzy-latest 'echo -n "ros: "; ls /opt/ros; echo -n "ydlidar drv: "; ls /opt/navlab_sensor_ws/install 2>/dev/null | head -3; echo -n "venv py: "; /opt/gazebo-sensor-venv/bin/python --version 2>/dev/null'
chk navlab/fast-lio:jazzy-latest 'echo -n "ros: "; ls /opt/ros; test -f /usr/local/lib/liblivox_lidar_sdk_shared.so && echo livox_so_OK; ls /workspace/ros_ws/install 2>/dev/null | grep -E "fast_lio|livox" | head'
chk navlab/companion:jazzy-09a5aa472901 'echo -n "ros: "; ls /opt/ros; python3 --version'
chk navlab/ardupilot-sitl:jazzy-latest 'echo -n "arducopter: "; find / -name arducopter -type f 2>/dev/null | head -1; echo -n "sim_vehicle: "; find / -name sim_vehicle.py 2>/dev/null | head -1'
chk navlab/mavlink-router:jazzy-latest 'command -v mavlink-routerd && echo routerd_OK'
echo "────────── DONE"
