#!/usr/bin/env bash
# run_light.sh 的 host 网络变体(阶段2 桥接用):ros1_bridge 容器要连本容器的
# ROS1 master(localhost:11311),bridge 网络下 ROS_HOSTNAME=localhost 无法被外部回连,
# host 网络下桥与本容器同 localhost,TCPROS 直通。其余与 run_light.sh 完全一致。
set -euo pipefail
cd "$(dirname "$0")"

docker rm -f gbplanner_ref >/dev/null 2>&1 || true
docker run -d \
  --network host \
  -e DISPLAY="${DISPLAY:-:0}" -e WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}" \
  -e XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir -e PULSE_SERVER=/mnt/wslg/PulseServer \
  -e LIBGL_ALWAYS_SOFTWARE=1 -e GALLIUM_DRIVER=llvmpipe \
  -e ROS_HOSTNAME=localhost -e ROS_MASTER_URI=http://localhost:11311 -e ROS_IP=127.0.0.1 \
  -e PYTHONUNBUFFERED=1 \
  -v /tmp/.X11-unix:/tmp/.X11-unix -v /mnt/wslg:/mnt/wslg \
  -v "$(pwd)/light_boxes.world:/root/light_boxes.world:ro" \
  --name gbplanner_ref gbplanner-ref:latest \
  bash -c 'sed -i "s/ gpu=\"true\"//; s/ organize_cloud=\"true\"//" /root/gbp_ws/src/sim/rotors_simulator/rotors_description/urdf/rmf_obelix_base.xacro && source /opt/ros/noetic/setup.bash && source /root/gbp_ws/devel/setup.bash && roslaunch gbplanner rmf_sim.launch world_file:=/root/light_boxes.world'

echo "已启动(host 网络)。桥容器用 ROS_MASTER_URI=http://localhost:11311 即可连。"
