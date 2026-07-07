#!/usr/bin/env bash
# GUI2·GBPlanner RViz(WSLg)——接到 gbplanner_ref 的 ROS1 master(host 网络 localhost:11311)
# 前提:gbplanner_ref 在跑(wm_planner.launch 自启)。演示口径=阶段性可视化,对象按 topic 讲不按颜色。
set -o pipefail
IMG=gbplanner-ref:latest
docker run --rm -d --name gbp_rviz --network host \
  -e DISPLAY="${DISPLAY:-:0}" -e WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}" \
  -e XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir -e PULSE_SERVER=/mnt/wslg/PulseServer \
  -e ROS_MASTER_URI=http://localhost:11311 -e ROS_HOSTNAME=localhost \
  -e LIBGL_ALWAYS_SOFTWARE=1 \
  -v /tmp/.X11-unix:/tmp/.X11-unix -v /mnt/wslg:/mnt/wslg \
  "$IMG" bash -c '
    source /opt/ros/noetic/setup.bash && source /root/gbp_ws/devel/setup.bash
    CFG=$(find /root/gbp_ws/src -name "*.rviz" 2>/dev/null | grep -iE "rmf|uav|aerial" | head -1)
    [ -z "$CFG" ] && CFG=$(find /root/gbp_ws/src -name "*.rviz" 2>/dev/null | grep -i gbplanner | head -1)
    [ -z "$CFG" ] && CFG=$(find /root/gbp_ws/src -name "*.rviz" 2>/dev/null | head -1)
    echo "RVIZ CONFIG: $CFG"
    rosrun rviz rviz ${CFG:+-d "$CFG"}'
echo "RViz 启动中(容器 gbp_rviz)。看不到窗口时:docker logs gbp_rviz"
echo "手动添加显示(Add→By topic):/wm/points(输入点云)、/gbplanner_node/tsdf_pointcloud(voxblox)、/rmf_obelix/command/trajectory 无法直接显示,轨迹看 /vis/* markers(仅可视化,不进控制链)"
