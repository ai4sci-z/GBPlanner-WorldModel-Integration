#!/usr/bin/env bash
# GUI-A·原版 GBPlanner 官方仿真(预研B 一键,2026-07-02 实测调通的全部修复固化)
# 独立容器名 gbplanner_orig + 独立 bridge 网络,与融合栈(gbplanner_ref, host网)互不干扰。
# RViz 弹窗后:左下 GbPlanner Control → Initialization → Start Planner 触发自主探索;
# 或直接跑本目录 takeoff 命令(见脚本末尾提示)。
set -euo pipefail
cd /mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/gbplanner_ref

docker rm -f gbplanner_orig >/dev/null 2>&1 || true
docker run -d \
  -e DISPLAY="${DISPLAY:-:0}" -e WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}" \
  -e XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir -e PULSE_SERVER=/mnt/wslg/PulseServer \
  -e LIBGL_ALWAYS_SOFTWARE=1 -e GALLIUM_DRIVER=llvmpipe \
  -e ROS_HOSTNAME=localhost -e ROS_MASTER_URI=http://localhost:11311 -e ROS_IP=127.0.0.1 \
  -e PYTHONUNBUFFERED=1 \
  -v /tmp/.X11-unix:/tmp/.X11-unix -v /mnt/wslg:/mnt/wslg \
  -v "$(pwd)/light_boxes.world:/root/light_boxes.world:ro" \
  --name gbplanner_orig gbplanner-ref:latest \
  bash -c 'sed -i "s/ gpu=\"true\"//; s/ organize_cloud=\"true\"//" /root/gbp_ws/src/sim/rotors_simulator/rotors_description/urdf/rmf_obelix_base.xacro && source /opt/ros/noetic/setup.bash && source /root/gbp_ws/devel/setup.bash && roslaunch gbplanner rmf_sim.launch world_file:=/root/light_boxes.world'

echo "GUI-A 启动中:约 20~30 秒后 RViz 弹到桌面(原版 GBPlanner,RotorS 仿真,box 世界)。"
echo "等 RViz 出现后,起飞+自动探索一键:"
echo "  bash $(dirname "$0")/gui_demo_A_takeoff.sh"
echo "(或 RViz 左下 GbPlanner Control → Initialization → Start Planner)"
