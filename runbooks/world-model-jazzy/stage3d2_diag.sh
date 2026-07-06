#!/usr/bin/env bash
# 3D 诊断②:栈存活窗口内查 ①/cloud_in 发布者(ROS graph) ②gz 侧 lidar 话题清单
# ③gz /lidar/points 的实际内容(点数,判 3D) ④渲染后的 bridge 配置里 lidar 条目。
set -o pipefail
export PATH=/usr/local/go/bin:$PATH
export NAVLAB_SIM_DISTRO=jazzy
CLEAN=/home/ai4s/ws-clean/world-model
OUT=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/stage3d2_evidence.txt
JAZZY_IMG=navlab/official-baseline:jazzy-latest
URI='<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'

{
echo "=== STAGE3D2 DIAG START $(date) ==="
echo "--- 1. 后台起栈 ---"
cd "$CLEAN/orchestration/sim" || exit 9
go run ./cmd/navlab-sim run exploration --live-preflight > /home/ai4s/s3d2_run.log 2>&1 &
RUN_PID=$!
for i in $(seq 1 40); do
  sleep 3
  N=$(docker ps --format '{{.Names}}' | grep -c navlab)
  if [ "$N" -ge 5 ]; then echo "  stack up t=$((i*3))s"; break; fi
done
sleep 15

echo "--- 2. gz 侧话题清单(gazebo 容器内,找 lidar/points) ---"
GZC=$(docker ps --format '{{.Names}} {{.Image}}' | grep -E "gazebo-sensor|official-baseline" | awk "{print \$1}" | head -1)
echo "gz container=$GZC"
docker ps --format '{{.Names}}\t{{.Image}}' | head -12
for C in $(docker ps --format '{{.Names}}'); do
  R=$(docker exec "$C" bash -c "source /opt/ros/jazzy/setup.bash 2>/dev/null; gz topic -l 2>/dev/null | grep -iE 'lidar|points|scan' | head -8" 2>/dev/null)
  if [ -n "$R" ]; then echo "== [$C] gz topics:"; echo "$R"; break; fi
done

echo "--- 3. gz /lidar/points 内容采样(点数/字段) ---"
for C in $(docker ps --format '{{.Names}}'); do
  R=$(docker exec "$C" bash -c "source /opt/ros/jazzy/setup.bash 2>/dev/null; timeout 6 gz topic -e -n1 -t /lidar/points 2>/dev/null | head -20" 2>/dev/null)
  if [ -n "$R" ]; then echo "== [$C] /lidar/points sample:"; echo "$R" | grep -E "width|height|count|field|name" | head -10; break; fi
done

echo "--- 4. /cloud_in 的 ROS 发布者(graph) ---"
docker run --rm --network host \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  "$JAZZY_IMG" bash -lc "timeout 20 ros2 topic info /cloud_in --verbose 2>&1 | grep -E 'Node name|Topic type|Endpoint type' | head -12"

echo "--- 5. run 渲染出的 bridge 配置里 lidar/cloud 条目 ---"
RUN=$(ls -t "$CLEAN/artifacts/sim/exploration" | head -1)
grep -rn -iE "lidar|cloud" "$CLEAN/artifacts/sim/exploration/$RUN/runtime" --include="*.yaml" | head -12 || echo "(no yaml matches)"
find "$CLEAN/artifacts/sim/exploration/$RUN" -name "*.yaml" | head -8

echo "--- 6. 等 run 结束(不关心 rc) ---"
wait $RUN_PID
echo "=== STAGE3D2 DIAG END $(date) ==="
} 2>&1 | tee "$OUT"
