#!/usr/bin/env bash
# GUI1·Gazebo 主仿真界面(WSLg)——附着到正在运行的 gz server(live run 期间执行)
# 原理:gz GUI 经 gz-transport 发现同机 server;host 网络+同 partition 即可。
set -o pipefail
IMG=navlab/gazebo-headless:jazzy-latest
docker run --rm -d --name wm_gzgui --network host \
  -e DISPLAY="${DISPLAY:-:0}" -e WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}" \
  -e XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir -e PULSE_SERVER=/mnt/wslg/PulseServer \
  -e LIBGL_ALWAYS_SOFTWARE=1 -e QT_X11_NO_MITSHM=1 \
  -v /tmp/.X11-unix:/tmp/.X11-unix -v /mnt/wslg:/mnt/wslg \
  "$IMG" bash -lc 'gz sim -g'
echo "Gazebo GUI 启动中(容器 wm_gzgui)。没窗口时:docker logs wm_gzgui;"
echo "若 partition 不匹配收不到场景:live run 的 gz server 在 world-model 的 gazebo 容器内,"
echo "可改用 fallback:RViz(GUI2)+ 结果面板(GUI3)撑住演示。"
