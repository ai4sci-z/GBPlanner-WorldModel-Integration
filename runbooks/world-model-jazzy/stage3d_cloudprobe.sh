#!/usr/bin/env bash
# 3D 第一步:world-model 栈(clean_repro 后台)存活窗口内,用 cloud_z_probe 实证
# 图上 PointCloud2 话题与 z 分布(判据:zmax-zmin>0.3 = 真 3D)。
set -o pipefail
export PATH=/usr/local/go/bin:$PATH
export NAVLAB_SIM_DISTRO=jazzy
CLEAN=/home/ai4s/ws-clean/world-model
BR=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/integration/ros1_bridge
OUT=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/stage3d_evidence.txt
JAZZY_IMG=navlab/official-baseline:jazzy-latest
URI='<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'

{
echo "=== STAGE3D CLOUD PROBE START $(date) ==="
# 停掉 2.6 遗留栈避免资源/端口干扰(gbplanner_ref 是 ROS1,不冲突 DDS,但省 CPU)
docker rm -f thin_ros2 s3_dry >/dev/null 2>&1 || true

echo "--- 1. 后台起 world-model exploration 栈 ---"
cd "$CLEAN/orchestration/sim" || exit 9
go run ./cmd/navlab-sim run exploration --live-preflight > /home/ai4s/s3d_run.log 2>&1 &
RUN_PID=$!

echo "--- 2. 等栈起来(容器数>=6) ---"
for i in $(seq 1 40); do
  sleep 3
  N=$(docker ps --format '{{.Names}}' | grep -c navlab)
  if [ "$N" -ge 5 ]; then echo "  stack up at t=$((i*3))s (navlab containers=$N)"; break; fi
done
sleep 12

echo "--- 3. 采样所有 PointCloud2 话题的 z 分布(60s 窗口) ---"
docker run --rm --network host \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  -v "$BR":/exp:ro "$JAZZY_IMG" bash -lc "timeout 70 python3 /exp/cloud_z_probe.py"

echo "--- 4. 等 run 结束 ---"
wait $RUN_PID
tail -4 /home/ai4s/s3d_run.log
echo "=== STAGE3D CLOUD PROBE END $(date) ==="
} 2>&1 | tee "$OUT"
