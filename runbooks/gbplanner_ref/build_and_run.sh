#!/usr/bin/env bash
# 在 WSL2 Ubuntu 内运行:构建并启动 GBPlanner 参考 sim(GUI 经 WSLg 转发)
# 用法: bash build_and_run.sh           # 构建并跑 rmf_sim.launch
#       bash build_and_run.sh shell     # 只进容器 shell,不自动 launch
set -euo pipefail
cd "$(dirname "$0")"

IMG=gbplanner-ref
echo "==> docker build $IMG (首次会拉 voxblox 等并编译,约 10–25 分钟)"
docker build -t "$IMG" .

# WSLg GUI 转发(X11 + Wayland)。GPU 默认走软件渲染最稳;
# 想用 RTX5060 硬件加速:先装 nvidia-container-toolkit,再给 docker run 加 --gpus all 并去掉 LIBGL_ALWAYS_SOFTWARE。
COMMON_ARGS=(
  -it --rm --net=host
  -e DISPLAY="${DISPLAY:-:0}"
  -e WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
  -e XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir
  -e PULSE_SERVER="${PULSE_SERVER:-/mnt/wslg/PulseServer}"
  -e LIBGL_ALWAYS_SOFTWARE=1
  -v /tmp/.X11-unix:/tmp/.X11-unix
  -v /mnt/wslg:/mnt/wslg
  --name gbplanner_ref
)

if [[ "${1:-}" == "shell" ]]; then
  docker run "${COMMON_ARGS[@]}" "$IMG" bash
else
  echo "==> 启动 rmf_sim.launch(RViz 看 velodyne 点云 + 探索图 + 航点)"
  docker run "${COMMON_ARGS[@]}" "$IMG" bash -lc "roslaunch gbplanner rmf_sim.launch"
fi
