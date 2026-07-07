#!/usr/bin/env bash
# 追加一个 C 视角 RViz(gbp_rviz2)——不动任何既有窗口/容器,纯新增
set -o pipefail
IMG=gbplanner-ref:latest
docker run -d --name gbp_rviz2 --network host \
  -e DISPLAY="${DISPLAY:-:0}" -e WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}" \
  -e XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir -e PULSE_SERVER=/mnt/wslg/PulseServer \
  -e ROS_MASTER_URI=http://localhost:11311 -e ROS_HOSTNAME=localhost \
  -e LIBGL_ALWAYS_SOFTWARE=1 -e GALLIUM_DRIVER=llvmpipe -e QT_X11_NO_MITSHM=1 \
  -v /tmp/.X11-unix:/tmp/.X11-unix -v /mnt/wslg:/mnt/wslg \
  "$IMG" bash -c '
    source /opt/ros/noetic/setup.bash && source /root/gbp_ws/devel/setup.bash
    CFG=$(find /root/gbp_ws/src -name "*.rviz" 2>/dev/null | grep -iE "rmf|uav|aerial" | head -1)
    [ -z "$CFG" ] && CFG=$(find /root/gbp_ws/src -name "*.rviz" 2>/dev/null | grep -i gbplanner | head -1)
    echo "RVIZ2 CONFIG: $CFG"
    rosrun rviz rviz ${CFG:+-d "$CFG"}'
echo "第二个 C 视角 RViz(gbp_rviz2)启动中——与现有窗口互不影响。"
