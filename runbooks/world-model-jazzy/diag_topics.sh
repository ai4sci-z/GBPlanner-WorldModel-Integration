#!/usr/bin/env bash
# 定位断点:起一个临时 run 时抓活体 ROS2 话题,看 /ap/v1/pose/filtered、外部导航、tf 到底有没有。
# 直接在 official-baseline 容器网络里查(它是 AP_DDS 的家)。
set -o pipefail
echo "=== 当前有没有跑着的容器 ==="
docker ps --format "{{.Names}}\t{{.Status}}" | head -12
BASE=/home/ai4s/ws/world-model/artifacts/sim/exploration
RUN="$(ls -t "$BASE" | head -1)"
D="$BASE/$RUN"
echo "=== run: $RUN ==="
echo "=== 该 run 的 probe 结果(exploration_probe/frame_contract_probe 实际抓到啥) ==="
for f in "$D"/probes/*; do
  [ -f "$f" ] || continue
  echo "----- $(basename "$f")"
  head -c 1500 "$f"; echo
done
echo "=== rosbag 里真实录到的话题(证明哪些 topic 真的有数据) ==="
BAG=$(find "$D/rosbag" -name "*.mcap" 2>/dev/null | head -1)
echo "bag=$BAG"
if [ -n "$BAG" ]; then
  docker run --rm -v "$D/rosbag:/bag:ro" --entrypoint bash navlab/official-baseline:jazzy-latest -c \
    "source /opt/ros/jazzy/setup.bash && ros2 bag info /bag/$(basename "$BAG") 2>/dev/null | grep -A200 Topic" 2>&1 | head -40
fi
