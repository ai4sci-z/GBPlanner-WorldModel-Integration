#!/usr/bin/env bash
# GUI-C·长驻演示 run(仅演示用):探索窗口临时 26s→600s,数据流持续 ~10 分钟,
# 期间 RViz 里体素图持续生长、Start/Stop Planner 实时有反应。跑完自动还原配置。
# 不动任何既有窗口;要求桥栈已在(gbplanner_ref/thin_ros2/s4_adapter)。
set -o pipefail
export PATH=/usr/local/go/bin:$PATH
export NAVLAB_SIM_DISTRO=jazzy
CLEAN=/home/ai4s/ws-clean/world-model
YAML=$CLEAN/orchestration/sim/configs/tasks/exploration.yaml
JAZZY_IMG=navlab/official-baseline:jazzy-latest
URI='<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'
E() { docker exec gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; $1"; }
restore() {
  sed -i 's/strategy: external/strategy: frontier_lite/' "$YAML"
  sed -i 's/exploration_window_sec: 600.0/exploration_window_sec: 26.0/' "$YAML"
}
trap restore EXIT

DIRB=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/integration/ros1_bridge
docker ps --format '{{.Names}}' | grep -q '^gbplanner_ref$' || { echo "缺 gbplanner_ref(planner 容器)"; exit 1; }
docker exec gbplanner_ref bash -c 'pgrep -f thinbridge_ros1 >/dev/null' || \
  docker exec -d gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; python3 /tmp/thinbridge_ros1_side.py > /tmp/thinbridge_ros1.log 2>&1"
# 喂料容器缺则自建(不打扰既有的)
docker ps --format '{{.Names}}' | grep -q '^thin_ros2$' || \
  docker run -d --network host --name thin_ros2 \
    -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
    -v "$DIRB":/exp:ro "$JAZZY_IMG" bash -lc "python3 /exp/thinbridge_ros2_side.py"
docker ps --format '{{.Names}}' | grep -q '^s4_adapter$' || \
  docker run -d --network host --name s4_adapter \
    -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
    -v "$DIRB":/exp:ro "$JAZZY_IMG" bash -lc "python3 /exp/trajectory_to_intent_stage4.py"

echo "=== 演示配置:external + 窗口 600s(结束自动还原)==="
sed -i 's/strategy: frontier_lite/strategy: external/' "$YAML"
sed -i 's/exploration_window_sec: 26.0/exploration_window_sec: 600.0/' "$YAML"
grep -nE 'strategy:|exploration_window_sec:' "$YAML" | head -2

cd "$CLEAN/orchestration/sim" || exit 9
go run ./cmd/navlab-sim run exploration --live-preflight > /home/ai4s/gui_c_long.log 2>&1 &
RUN_PID=$!
sleep 30
docker run --rm --network host -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" "$JAZZY_IMG" \
  bash -lc "timeout 5 ros2 topic pub /gbp/enable std_msgs/msg/Bool '{data: true}' -r 2 >/dev/null 2>&1; echo enabled"
E "timeout 10 rosservice call /planner_control_interface/std_srvs/automatic_planning '{}' 2>&1 | head -2"
echo ">>> 长驻演示进行中(~10 分钟):看 C 的 RViz,体素图持续生长;Start/Stop Planner 可交互 <<<"
wait $RUN_PID
tail -2 /home/ai4s/gui_c_long.log
restore
echo "=== 长驻演示结束,配置已还原;再来一轮重跑本脚本 ==="
