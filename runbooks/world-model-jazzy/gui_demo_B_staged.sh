#!/usr/bin/env bash
# GUI-B·原版 world-model 分级起飞演示(最小链,逐级检查点):
#  [1] 起 live run(frontier_lite,任务链会自动:启 Gazebo→FCU→SLAM→takeoff→探索→降落)
#  [2] 检查仿真活着(传感器话题在跳)
#  [3] 附着全新 Gazebo GUI 窗口(wm_gzgui2,不动旧窗口)→ 你能看到 iris
#  [4] takeoff_watch:实时打印飞控 z 爬升(离地铁证)
#  [5] run 自然结束(探索+降落)
# 重要:起飞不是在 Gazebo 里点的,是任务链自动发的;Gazebo 只是世界视图。
set -o pipefail
export PATH=/usr/local/go/bin:$PATH
export NAVLAB_SIM_DISTRO=jazzy
CLEAN=/home/ai4s/ws-clean/world-model
DIRB=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/integration/ros1_bridge
JAZZY_IMG=navlab/official-baseline:jazzy-latest
URI='<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'

echo "=== [0] 保证'原版'纯净:撤掉融合喂料(s4_adapter/thin_ros2 会混流) ==="
docker rm -f thin_ros2 s4_adapter s5c_probe >/dev/null 2>&1 || true
grep -n 'strategy:' "$CLEAN/orchestration/sim/configs/tasks/exploration.yaml" | head -1

echo "=== [1] 起 live run(frontier_lite)——任务链自动完成起飞/探索/降落 ==="
cd "$CLEAN/orchestration/sim" || exit 9
go run ./cmd/navlab-sim run exploration --live-preflight > /home/ai4s/gui_b_staged.log 2>&1 &
RUN_PID=$!
# 起飞观察器立刻后台开(从 z=0 全程盯,不错过爬升)
docker rm -f b_watch >/dev/null 2>&1 || true
docker run -d --name b_watch --network host -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  -v "$DIRB":/exp:ro "$JAZZY_IMG" bash -lc "python3 /exp/takeoff_watch.py; sleep 300" >/dev/null

echo "=== [2] 等仿真活起来(gazebo 容器 + 传感器话题) ==="
for i in $(seq 1 40); do
  docker ps --format '{{.Names}}' | grep -q '^navlab-official-baseline$' && break; sleep 3
done
docker ps --format '{{.Names}}' | grep -q '^navlab-official-baseline$' && echo "✓ gazebo/SITL 容器已起" || echo "✗ 容器未起,看 /home/ai4s/gui_b_staged.log"
docker run --rm --network host -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" "$JAZZY_IMG" \
  bash -lc "timeout 12 ros2 topic hz /scan 2>&1 | grep -m1 average && echo '✓ 仿真在跑(/scan 有频率=Sim time 在走)' || echo '…/scan 未见(可能还在启动)'"

echo "=== [3] 附着全新 Gazebo GUI(wm_gzgui2,旧窗口不动)——看 iris ==="
GZP=""
SRV_HN=$(docker exec navlab-official-baseline hostname 2>/dev/null)
SRV_UN=$(docker exec navlab-official-baseline whoami 2>/dev/null || echo root)
GZP="$SRV_HN:$SRV_UN"
echo "GZ_PARTITION=$GZP"
docker rm -f wm_gzgui2 >/dev/null 2>&1 || true
docker run -d --name wm_gzgui2 --network host \
  -e GZ_PARTITION="$GZP" \
  -e GZ_SIM_RESOURCE_PATH=/opt/ardupilot_gazebo/models:/opt/ardupilot_gazebo/worlds \
  -e DISPLAY="${DISPLAY:-:0}" -e WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}" \
  -e XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir -e PULSE_SERVER=/mnt/wslg/PulseServer \
  -e LIBGL_ALWAYS_SOFTWARE=1 -e QT_X11_NO_MITSHM=1 \
  -v /tmp/.X11-unix:/tmp/.X11-unix -v /mnt/wslg:/mnt/wslg \
  navlab/official-baseline:jazzy-latest bash -lc 'gz sim -g --force-version 8'
echo "(若窗口空:等 30s;它只在 run 存活期有画面)"

echo "=== [4] takeoff_watch 实时输出(离地铁证;已从 run 起点全程盯) ==="
for i in $(seq 1 30); do
  docker logs b_watch 2>&1 | grep -q "TAKEOFF CONFIRMED" && break; sleep 5
done
docker logs b_watch 2>&1 | grep -E "z=|TAKEOFF|end" | tail -12

echo "=== [5] 等 run 自然结束(探索+降落) ==="
wait $RUN_PID
tail -2 /home/ai4s/gui_b_staged.log
echo "=== GUI-B 分级演示结束(Gazebo 窗口画面随 server 消失属正常) ==="
