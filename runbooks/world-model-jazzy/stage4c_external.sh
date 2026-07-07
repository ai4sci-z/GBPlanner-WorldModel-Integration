#!/usr/bin/env bash
# Stage4c·external 去混流联跑:证明无 frontier_lite 混流时,GBPlanner intent 使飞机产生可归因运动。
# 验收:external_strategy_active + no_frontier_intent + gbp_intent>0 + GBP签名cmd_vel>0
#      + odom path(签名活跃窗口)>=0.10m + takeoff_ok。跑完自动还原 exploration.yaml。
set -o pipefail
export PATH=/usr/local/go/bin:$PATH
export NAVLAB_SIM_DISTRO=jazzy
CLEAN=/home/ai4s/ws-clean/world-model
DIRB=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/integration/ros1_bridge
OUT=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/stage4c_external_evidence.txt
YAML=$CLEAN/orchestration/sim/configs/tasks/exploration.yaml
JAZZY_IMG=navlab/official-baseline:jazzy-latest
URI='<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'
E() { docker exec gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; $1"; }
JRUN() { docker run --rm --network host -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" "$JAZZY_IMG" bash -lc "$1"; }
restore_yaml() { sed -i 's/strategy: external/strategy: frontier_lite/' "$YAML"; }
trap restore_yaml EXIT

{
echo "=== STAGE4C START $(date) ==="
echo "--- 0. config 切 external(trap 保证还原) ---"
grep -n 'strategy:' "$YAML"
sed -i 's/strategy: frontier_lite/strategy: external/' "$YAML"
grep -n 'strategy:' "$YAML"

echo "--- 1. 栈复位(GBPlanner+薄桥+适配器+4c归因探针) ---"
docker rm -f thin_ros2 s4_adapter s4_cmdvel s4c_probe >/dev/null 2>&1 || true
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

echo "--- 2. world-model 真栈起(strategy=external) ---"
cd "$CLEAN/orchestration/sim" || exit 9
go run ./cmd/navlab-sim run exploration --live-preflight > /home/ai4s/s4c_run.log 2>&1 &
RUN_PID=$!
sleep 30

echo "--- 3. ENABLE(提早)+ 触发规划 ---"
JRUN "timeout 5 ros2 topic pub /gbp/enable std_msgs/msg/Bool '{data: true}' -r 2 >/dev/null 2>&1; echo enabled"
E "timeout 10 rosservice call /planner_control_interface/std_srvs/automatic_planning '{}' 2>&1 | head -2"
sleep 40
echo "--- 3b. 二次触发规划(防轨迹超龄断档) ---"
E "timeout 10 rosservice call /planner_control_interface/std_srvs/automatic_planning '{}' 2>&1 | head -2"
sleep 20

echo "--- 4. 适配器运动日志(尾8条) ---"
docker logs s4_adapter 2>&1 | grep -E "INTENT|TRAJ#" | tail -8

echo "--- 5. 等 run 结束 ---"
wait $RUN_PID
tail -3 /home/ai4s/s4c_run.log

echo "--- 6. 还原 config ---"
restore_yaml
grep -n 'strategy:' "$YAML"

echo "--- 7. run artifacts:external 直证 + takeoff ---"
RUNDIR=$(ls -td "$CLEAN"/artifacts/sim/exploration/*/ 2>/dev/null | head -1)
echo "RUNDIR=$RUNDIR"
grep -rl '"strategy": *"external"\|\\"strategy\\": *\\"external\\"\|strategy.*external' "$RUNDIR" 2>/dev/null | head -5
SUMMARY=$(find "$RUNDIR" -name summary.json | head -1)
echo "SUMMARY=$SUMMARY"
python3 - "$SUMMARY" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception as e:
    print("summary_parse_error:", e); sys.exit(0)
def walk(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            kl = str(k).lower()
            if any(t in kl for t in ("takeoff", "strategy", "status", "probe", "blocker")) and not isinstance(v, (dict, list)):
                print("%s.%s=%s" % (path, k, v))
            walk(v, path + "." + str(k))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            walk(v, "%s[%d]" % (path, i))
walk(d)
PY

echo "--- 8. 归因探针总结(等窗口收口) ---"
for i in $(seq 1 40); do
  docker logs s4c_probe 2>&1 | grep -q "PROBE_VERDICT" && break
  sleep 5
done
docker logs s4c_probe 2>&1 | tail -30

echo "--- 9. STAGE4C 汇总判定 ---"
PROBELOG=$(docker logs s4c_probe 2>&1)
TAKEOFF=$(python3 - "$SUMMARY" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print("unknown"); sys.exit(0)
found = []
def walk(o):
    if isinstance(o, dict):
        for k, v in o.items():
            if "takeoff" in str(k).lower() and isinstance(v, dict) and "ok" in v:
                found.append(bool(v["ok"]))
            if str(k).lower() == "name" and "takeoff" in str(v).lower() and isinstance(o.get("ok"), bool):
                found.append(bool(o["ok"]))
            walk(v)
    elif isinstance(o, list):
        for v in o:
            walk(v)
walk(d)
print("True" if (found and all(found)) else ("unknown" if not found else "False"))
PY
)
echo "takeoff_ok(summary)=$TAKEOFF"
echo "$PROBELOG" | grep -E "no_frontier_intent|frontier_intent=|gbp_intent=|gbp_motion_intent=|gbp_sig=|path_cmd_active_m=|path_from_first_gbp_m=|odom_z_max=|PROBE_VERDICT"
if echo "$PROBELOG" | grep -q "PROBE_VERDICT=PASS"; then
  if [ "$TAKEOFF" = "True" ]; then echo "STAGE4C=PASS"; else echo "STAGE4C=PARTIAL(probe过,takeoff字段=$TAKEOFF,须人工核对summary)"; fi
else
  echo "STAGE4C=FAIL(见探针总结定位卡点)"
fi
docker rm -f s4c_probe >/dev/null 2>&1 || true
echo "=== STAGE4C END $(date) ==="
} 2>&1 | tee "$OUT"
