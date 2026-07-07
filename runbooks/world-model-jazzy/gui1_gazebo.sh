#!/usr/bin/env bash
# GUI1·Gazebo 主仿真界面(WSLg)——附着到 live run 的 gz server(容器 navlab-official-baseline)
# 黑屏两大原因已修:①无 live run(server 不存在)②GUI 容器缺模型资源(须用 baseline 同款镜像)
set -o pipefail
IMG=navlab/official-baseline:jazzy-latest
GZP=""
# runner 先渲染产物再起容器,server 可能晚 ~60s 才出现——等它,不然分区算不到
for i in $(seq 1 30); do
  docker ps --format '{{.Names}}' | grep -q '^navlab-official-baseline$' && break
  sleep 3
done
if docker ps --format '{{.Names}}' | grep -q '^navlab-official-baseline$'; then
  # gz-transport 发现分区默认= hostname:username,两容器必须一致否则 GUI 永远黑屏
  SRV_HN=$(docker exec navlab-official-baseline hostname 2>/dev/null)
  SRV_UN=$(docker exec navlab-official-baseline whoami 2>/dev/null || echo root)
  SRV_GZP=$(docker exec navlab-official-baseline printenv GZ_PARTITION 2>/dev/null)
  GZP=${SRV_GZP:-"$SRV_HN:$SRV_UN"}
  echo "对齐发现分区 GZ_PARTITION=$GZP(server=$SRV_HN user=$SRV_UN)"
else
  echo "⚠️ live run 未在进行(无 navlab-official-baseline 容器)——先跑 gui_demo_master.sh,"
  echo "   run 进行中的 ~6 分钟内才有画面。"
fi
docker rm -f wm_gzgui >/dev/null 2>&1 || true
docker run --rm -d --name wm_gzgui --network host \
  ${GZP:+-e GZ_PARTITION="$GZP"} \
  -e GZ_SIM_RESOURCE_PATH=/opt/ardupilot_gazebo/models:/opt/ardupilot_gazebo/worlds \
  -e DISPLAY="${DISPLAY:-:0}" -e WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}" \
  -e XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir -e PULSE_SERVER=/mnt/wslg/PulseServer \
  -e LIBGL_ALWAYS_SOFTWARE=1 -e QT_X11_NO_MITSHM=1 \
  -v /tmp/.X11-unix:/tmp/.X11-unix -v /mnt/wslg:/mnt/wslg \
  "$IMG" bash -lc 'gz sim -g --force-version 8'
echo "Gazebo GUI 启动中(容器 wm_gzgui)。没窗口/黑屏排查:docker logs wm_gzgui"
