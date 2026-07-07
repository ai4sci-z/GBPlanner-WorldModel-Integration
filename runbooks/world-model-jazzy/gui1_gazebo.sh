#!/usr/bin/env bash
# GUI1·Gazebo 主仿真界面(WSLg)——附着到 live run 的 gz server(容器 navlab-official-baseline)
# 黑屏两大原因已修:①无 live run(server 不存在)②GUI 容器缺模型资源(须用 baseline 同款镜像)
set -o pipefail
IMG=navlab/official-baseline:jazzy-latest
if ! docker ps --format '{{.Names}}' | grep -q '^navlab-official-baseline$'; then
  echo "⚠️ live run 未在进行(无 navlab-official-baseline 容器)——先跑 gui_demo_master.sh,"
  echo "   run 进行中的 ~6 分钟内才有画面。"
fi
docker rm -f wm_gzgui >/dev/null 2>&1 || true
docker run --rm -d --name wm_gzgui --network host \
  -e GZ_SIM_RESOURCE_PATH=/opt/ardupilot_gazebo/models:/opt/ardupilot_gazebo/worlds \
  -e DISPLAY="${DISPLAY:-:0}" -e WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}" \
  -e XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir -e PULSE_SERVER=/mnt/wslg/PulseServer \
  -e LIBGL_ALWAYS_SOFTWARE=1 -e QT_X11_NO_MITSHM=1 \
  -v /tmp/.X11-unix:/tmp/.X11-unix -v /mnt/wslg:/mnt/wslg \
  "$IMG" bash -lc 'gz sim -g --force-version 8'
echo "Gazebo GUI 启动中(容器 wm_gzgui)。没窗口/黑屏排查:docker logs wm_gzgui"
