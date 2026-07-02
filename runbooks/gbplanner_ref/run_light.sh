#!/usr/bin/env bash
# 一键启动 GBPlanner 官方仿真(轻量 box 世界,WSLg 软件渲染可稳跑)
# 固化 2026-07-02 实测调通的全部修复:
#   A 显式 source(bash -c 非交互不读 .bashrc)
#   B ROS_HOSTNAME=localhost(容器 hostname 只解析 IPv6,ROS1 卡死)
#   C sed 去掉 OS0-128 xacro 不接受的 gpu/organize_cloud 参数(上游 bug)
#   D 用纯 box 图元的 light_boxes.world(DARPA 网格大场景压垮 llvmpipe 软件渲染,gzserver 段错误)
#   E light_boxes.world 内含 ros_interface_plugin(缺它则 RotorS 里程计不转 ROS,voxblox 丢光点云)
# ⚠️ WSL 下需保持一个常驻进程吊住发行版(否则空闲自动关机杀掉 docker):
#   另开窗口跑 `wsl -d Ubuntu-22.04` 放着即可。
set -euo pipefail
cd "$(dirname "$0")"

docker rm -f gbplanner_ref >/dev/null 2>&1 || true
docker run -d \
  -e DISPLAY="${DISPLAY:-:0}" -e WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}" \
  -e XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir -e PULSE_SERVER=/mnt/wslg/PulseServer \
  -e LIBGL_ALWAYS_SOFTWARE=1 -e GALLIUM_DRIVER=llvmpipe \
  -e ROS_HOSTNAME=localhost -e ROS_MASTER_URI=http://localhost:11311 -e ROS_IP=127.0.0.1 \
  -e PYTHONUNBUFFERED=1 \
  -v /tmp/.X11-unix:/tmp/.X11-unix -v /mnt/wslg:/mnt/wslg \
  -v "$(pwd)/light_boxes.world:/root/light_boxes.world:ro" \
  --name gbplanner_ref gbplanner-ref:latest \
  bash -c 'sed -i "s/ gpu=\"true\"//; s/ organize_cloud=\"true\"//" /root/gbp_ws/src/sim/rotors_simulator/rotors_description/urdf/rmf_obelix_base.xacro && source /opt/ros/noetic/setup.bash && source /root/gbp_ws/devel/setup.bash && roslaunch gbplanner rmf_sim.launch world_file:=/root/light_boxes.world'

echo "已启动。约 20 秒后 RViz 弹到桌面;验证链路:"
echo "  docker exec gbplanner_ref bash -c 'source /opt/ros/noetic/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; rostopic hz /gbplanner_node/tsdf_pointcloud'"
echo "  (看到 average rate ≈4~5 = voxblox 3D 建图在跑)"
echo "触发探索:RViz 左下 GbPlanner Control → Initialization → Start Planner"
