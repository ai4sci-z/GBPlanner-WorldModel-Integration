#!/usr/bin/env bash
# 受控实验:后台起 clean_repro,等栈起来后在探针同款容器里跑 sub_latency_probe,
# 实测 /ap/v1/pose/filtered 从订阅到首条消息的真实耗时。只报实测。
set -o pipefail
export PATH=/usr/local/go/bin:$PATH
export NAVLAB_SIM_DISTRO=jazzy
CLEAN=/home/ai4s/ws-clean/world-model
SCRIPT=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/sub_latency_probe.py
URI='<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'

cd "$CLEAN/orchestration/sim" || exit 9
echo "=== start clean_repro in background ==="
go run ./cmd/navlab-sim run exploration --live-preflight > /home/ai4s/exp_run.log 2>&1 &
RUN_PID=$!

# 等 SITL/agent 起来:轮询 docker 里出现 sitl 相关容器 + 再等 pose 开始发布
echo "=== waiting for stack (polling ap pose publisher via throwaway container) ==="
FOUND=0
for i in $(seq 1 40); do
  sleep 3
  N=$(docker ps --format '{{.Names}}' | wc -l)
  echo "  t=$((i*3))s containers=$N"
  if [ "$N" -ge 6 ]; then FOUND=1; break; fi
done
if [ "$FOUND" != 1 ]; then echo "STACK_NEVER_CAME_UP"; kill $RUN_PID 2>/dev/null; exit 4; fi

echo "=== stack up, wait 12s more for SITL DDS agent ==="
sleep 12
echo "=== launching experiment container (same image/env/network as probe) ==="
docker run --rm --network host \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
  -e ROS_DOMAIN_ID=0 -e DDS_DOMAIN_ID=0 -e DDS_ENABLE=1 \
  -e CYCLONEDDS_URI="$URI" \
  -v /mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy:/exp:ro \
  navlab/official-baseline:jazzy-latest \
  bash -lc 'python3 /exp/sub_latency_probe.py /ap/v1/pose/filtered 40'
RC=$?
echo "=== experiment rc=$RC; waiting for run to finish ==="
wait $RUN_PID
echo "=== clean_repro finished (rc=$?) ; tail of run log ==="
tail -5 /home/ai4s/exp_run.log
