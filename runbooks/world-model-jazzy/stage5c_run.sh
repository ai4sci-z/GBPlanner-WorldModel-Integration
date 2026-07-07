#!/usr/bin/env bash
# Stage5c·单次同口径联跑(用法: stage5c_run.sh <runN>)——批跑由外层逐次调用
# 输出:runbooks/world-model-jazzy/stage5c_<runN>_evidence.txt(含 §7.3 对齐表)
set -o pipefail
export PATH=/usr/local/go/bin:$PATH
export NAVLAB_SIM_DISTRO=jazzy
N=${1:?usage: stage5c_run.sh <runN>}
CLEAN=/home/ai4s/ws-clean/world-model
DIRB=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/integration/ros1_bridge
OUT=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/stage5c_${N}_evidence.txt
YAML=$CLEAN/orchestration/sim/configs/tasks/exploration.yaml
JAZZY_IMG=navlab/official-baseline:jazzy-latest
URI='<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'
E() { docker exec gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; $1"; }
JRUN() { docker run --rm --network host -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" "$JAZZY_IMG" bash -lc "$1"; }
restore_yaml() { sed -i 's/strategy: external/strategy: frontier_lite/' "$YAML"; }
trap restore_yaml EXIT

{
echo "=== STAGE5C $N START $(date) ==="
sed -i 's/strategy: frontier_lite/strategy: external/' "$YAML"
docker rm -f thin_ros2 s4_adapter s5c_probe >/dev/null 2>&1 || true
docker restart gbplanner_ref >/dev/null
sleep 25
docker exec -d gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; python3 /tmp/thinbridge_ros1_side.py > /tmp/thinbridge_ros1.log 2>&1"
sleep 3
docker run -d --network host --name thin_ros2 \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  -v "$DIRB":/exp:ro "$JAZZY_IMG" bash -lc "python3 /exp/thinbridge_ros2_side.py"
docker run -d --network host --name s4_adapter \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  -v "$DIRB":/exp:ro "$JAZZY_IMG" bash -lc "python3 /exp/trajectory_to_intent_stage4.py"
docker run -d --network host --name s5c_probe \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  -v "$DIRB":/exp:ro "$JAZZY_IMG" bash -lc "python3 /exp/stage5c_probe.py; sleep 150"
sleep 5
cd "$CLEAN/orchestration/sim" || exit 9
go run ./cmd/navlab-sim run exploration --live-preflight > /home/ai4s/s5c_run.log 2>&1 &
RUN_PID=$!
sleep 30
JRUN "timeout 5 ros2 topic pub /gbp/enable std_msgs/msg/Bool '{data: true}' -r 2 >/dev/null 2>&1; echo enabled"
E "timeout 10 rosservice call /planner_control_interface/std_srvs/automatic_planning '{}' 2>&1 | head -2"
sleep 40
E "timeout 10 rosservice call /planner_control_interface/std_srvs/automatic_planning '{}' 2>&1 | head -2"
wait $RUN_PID
tail -2 /home/ai4s/s5c_run.log

echo "--- run 判定 ---"
RUNDIR=$(ls -td "$CLEAN"/artifacts/sim/exploration/*/ | head -1)
echo "RUNDIR=$RUNDIR"
python3 -c "
import json
d=json.load(open('$RUNDIR/summary.json'))
print('task_status =', d.get('status'))
print('gate.exploration =', json.dumps((d.get('metrics') or {}).get('gate',{}).get('exploration',{}), ensure_ascii=False))
"
grep -o 'required probes failed[^\"]*' /home/ai4s/s5c_run.log | head -1
docker logs s4_adapter 2>&1 | grep -cE "GATE OK" | xargs echo "gate_ok_latched="
docker logs s4_adapter 2>&1 | grep -E "GATE OK|WP REACHED" | tail -6
echo "--- §7.3 对齐表 ---"
for i in $(seq 1 40); do
  docker logs s5c_probe 2>&1 | grep -q "STAGE5C_PROBE_SUMMARY" && break
  sleep 5
done
docker logs s5c_probe 2>&1 | grep -vE "Failed to parse type hash" | sed -n '/STAGE5C_ALIGN_TABLE/,$p'
docker rm -f s5c_probe >/dev/null 2>&1 || true
restore_yaml
echo "=== STAGE5C $N END $(date) ==="
} 2>&1 | tee "$OUT"
