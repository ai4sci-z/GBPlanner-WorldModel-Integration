#!/usr/bin/env bash
# Stage5·轴向校准联跑:external 去混流 + cal_axis_probe(纯平移/零yaw)
# 产出:intent(+x/+y) → odom/ap 位移向量 → 映射矩阵实测
set -o pipefail
export PATH=/usr/local/go/bin:$PATH
export NAVLAB_SIM_DISTRO=jazzy
CLEAN=/home/ai4s/ws-clean/world-model
DIRB=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/integration/ros1_bridge
OUT=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/stage5cal_axis_evidence.txt
YAML=$CLEAN/orchestration/sim/configs/tasks/exploration.yaml
JAZZY_IMG=navlab/official-baseline:jazzy-latest
URI='<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'
restore_yaml() { sed -i 's/strategy: external/strategy: frontier_lite/' "$YAML"; }
trap restore_yaml EXIT

{
echo "=== STAGE5CAL START $(date) ==="
echo "--- 0. config 切 external ---"
sed -i 's/strategy: frontier_lite/strategy: external/' "$YAML"
grep -n 'strategy:' "$YAML"

echo "--- 1. 清适配器容器(校准探针独占 intent),起校准探针 ---"
docker rm -f s4_adapter s4c_probe cal_axis >/dev/null 2>&1 || true
docker run -d --network host --name cal_axis \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  -v "$DIRB":/exp:ro "$JAZZY_IMG" bash -lc "python3 /exp/cal_axis_probe.py; sleep 60"
sleep 3

echo "--- 2. world-model 真栈起(external) ---"
cd "$CLEAN/orchestration/sim" || exit 9
go run ./cmd/navlab-sim run exploration --live-preflight > /home/ai4s/s5cal_run.log 2>&1 &
RUN_PID=$!
wait $RUN_PID
tail -2 /home/ai4s/s5cal_run.log

echo "--- 3. 还原 config ---"
restore_yaml
grep -n 'strategy:' "$YAML"

echo "--- 4. 校准结果 ---"
for i in $(seq 1 30); do
  docker logs cal_axis 2>&1 | grep -q "CAL_DONE\|CAL_INCOMPLETE" && break
  sleep 5
done
docker logs cal_axis 2>&1 | grep -vE "Failed to parse type hash"
docker rm -f cal_axis >/dev/null 2>&1 || true
echo "=== STAGE5CAL END $(date) ==="
} 2>&1 | tee "$OUT"
