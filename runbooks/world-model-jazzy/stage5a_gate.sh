#!/usr/bin/env bash
# Stage5a·gate/status 严格对齐联跑:external 去混流 + 轴换修正 + 诚实 accepted_goals
# 验收(Review_016 §3.3):status ok=True(五条件闩锁)+ accepted_goals>=3(不含预到达)
#   + path>=0.35 + strategy=gbplanner + TASK_STATUS(或明确列出未过 probe)
set -o pipefail
export PATH=/usr/local/go/bin:$PATH
export NAVLAB_SIM_DISTRO=jazzy
CLEAN=/home/ai4s/ws-clean/world-model
DIRB=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/integration/ros1_bridge
OUT=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/stage5a_gate_evidence.txt
YAML=$CLEAN/orchestration/sim/configs/tasks/exploration.yaml
JAZZY_IMG=navlab/official-baseline:jazzy-latest
URI='<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'
E() { docker exec gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; $1"; }
JRUN() { docker run --rm --network host -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" "$JAZZY_IMG" bash -lc "$1"; }
restore_yaml() { sed -i 's/strategy: external/strategy: frontier_lite/' "$YAML"; }
trap restore_yaml EXIT

{
echo "=== STAGE5A START $(date) ==="
echo "--- 0. config 切 external ---"
sed -i 's/strategy: frontier_lite/strategy: external/' "$YAML"
grep -n 'strategy:' "$YAML"

echo "--- 1. 栈复位(重启 GBPlanner 清体素图 + 新适配器 + 归因探针) ---"
docker rm -f thin_ros2 s4_adapter s4c_probe cal_axis >/dev/null 2>&1 || true
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
docker run -d --network host --name s4c_probe \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  -v "$DIRB":/exp:ro "$JAZZY_IMG" bash -lc "python3 /exp/stage4c_probe.py; sleep 120"
sleep 5

echo "--- 2. world-model 真栈起(external) ---"
cd "$CLEAN/orchestration/sim" || exit 9
go run ./cmd/navlab-sim run exploration --live-preflight > /home/ai4s/s5a_run.log 2>&1 &
RUN_PID=$!
sleep 30

echo "--- 3. ENABLE + 规划三连触发(0/25/50s) ---"
JRUN "timeout 5 ros2 topic pub /gbp/enable std_msgs/msg/Bool '{data: true}' -r 2 >/dev/null 2>&1; echo enabled"
E "timeout 10 rosservice call /planner_control_interface/std_srvs/automatic_planning '{}' 2>&1 | head -2"
sleep 25
E "timeout 10 rosservice call /planner_control_interface/std_srvs/automatic_planning '{}' 2>&1 | head -2"
sleep 25
E "timeout 10 rosservice call /planner_control_interface/std_srvs/automatic_planning '{}' 2>&1 | head -2"
sleep 10

echo "--- 4. 适配器日志(TRAJ/GATE/INTENT 摘要) ---"
docker logs s4_adapter 2>&1 | grep -E "TRAJ#|GATE OK|MIXED" | tail -10
docker logs s4_adapter 2>&1 | grep -E "INTENT" | tail -5

echo "--- 5. 等 run 结束 ---"
wait $RUN_PID
tail -3 /home/ai4s/s5a_run.log

echo "--- 6. 还原 config ---"
restore_yaml
grep -n 'strategy:' "$YAML"

echo "--- 7. run summary:status/gate/exploration 判定 ---"
RUNDIR=$(ls -td "$CLEAN"/artifacts/sim/exploration/*/ 2>/dev/null | head -1)
echo "RUNDIR=$RUNDIR"
grep -l 'external' "$RUNDIR/runtime/scripts/exploration_workflow_runtime.py" 2>/dev/null && echo "external_strategy_active=True(渲染脚本直证)"
python3 - "$RUNDIR/summary.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
print("task_status =", d.get("status"))
ex = (d.get("metrics") or {}).get("gate", {}).get("exploration", {})
print("gate.exploration =", json.dumps(ex, ensure_ascii=False))
for p in (d.get("evidence") or {}).get("probeOutputs", []):
    pay = p.get("payload") or {}
    spec = pay.get("spec") or {}
    name = spec.get("StatusTopic") or spec.get("ExplorationStatusTopic") or spec.get("status_topic") or "?"
    print("probe status=%s spec_topic=%s" % (p.get("status"), name))
    smp = pay.get("samples") or {}
    st = smp.get("/navlab/exploration/status")
    if st:
        print("  exploration_status sample ok=%s rc=%s parsed=%s" % (
            st.get("ok"), st.get("return_code"),
            json.dumps(st.get("parsed", {}), ensure_ascii=False)[:400]))
PY

echo "--- 8. 归因探针总结 ---"
for i in $(seq 1 40); do
  docker logs s4c_probe 2>&1 | grep -q "PROBE_VERDICT" && break
  sleep 5
done
docker logs s4c_probe 2>&1 | grep -vE "Failed to parse type hash" | tail -22

echo "--- 9. STAGE5A 汇总 ---"
ADLOG=$(docker logs s4_adapter 2>&1)
echo "$ADLOG" | grep -c "GATE OK latched" | xargs echo "gate_ok_latched_lines="
PROBELOG=$(docker logs s4c_probe 2>&1)
echo "$PROBELOG" | grep -E "frontier_intent=|no_frontier_intent" | head -3
if echo "$ADLOG" | grep -q "GATE OK latched" && echo "$PROBELOG" | grep -q "no_frontier_intent=True"; then
  if grep -q '"status": *"TASK_STATUS_OK"\|TASK_STATUS_OK' /home/ai4s/s5a_run.log "$RUNDIR/summary.json" 2>/dev/null; then
    echo "STAGE5A=PASS(gate latch + 全绿)"
  else
    echo "STAGE5A=GATE_LATCHED(适配器五条件达成;run 整体状态见 summary,若非 OK 列出未过 probe)"
    grep -o 'required probes failed[^"]*' /home/ai4s/s5a_run.log | head -2
  fi
else
  echo "STAGE5A=FAIL(未达成 gate latch 或混流,见适配器/探针日志)"
fi
docker rm -f s4c_probe >/dev/null 2>&1 || true
echo "=== STAGE5A END $(date) ==="
} 2>&1 | tee "$OUT"
