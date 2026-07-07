#!/usr/bin/env bash
# GUI-C·循环续跑演示:planner/RViz/体素图不重启,标准 external run 连跑 N 轮自动续,
# 地图跨轮累积,近似连续可交互(每轮 ~6 分钟,轮间 ~1 分钟)。用法: gui_demo_C_loop.sh [N=5]
set -o pipefail
export PATH=/usr/local/go/bin:$PATH
export NAVLAB_SIM_DISTRO=jazzy
N=${1:-5}
CLEAN=/home/ai4s/ws-clean/world-model
DIRB=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/integration/ros1_bridge
YAML=$CLEAN/orchestration/sim/configs/tasks/exploration.yaml
JAZZY_IMG=navlab/official-baseline:jazzy-latest
URI='<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'
E() { docker exec gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; $1"; }
restore_yaml() { sed -i 's/strategy: external/strategy: frontier_lite/' "$YAML"; }
trap restore_yaml EXIT

docker ps --format '{{.Names}}' | grep -q '^gbplanner_ref$' || { echo "缺 gbplanner_ref"; exit 1; }
docker exec gbplanner_ref bash -c 'pgrep -f thinbridge_ros1 >/dev/null' || \
  docker exec -d gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; python3 /tmp/thinbridge_ros1_side.py > /tmp/thinbridge_ros1.log 2>&1"
docker ps --format '{{.Names}}' | grep -q '^thin_ros2$' || \
  docker run -d --network host --name thin_ros2 \
    -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
    -v "$DIRB":/exp:ro "$JAZZY_IMG" bash -lc "python3 /exp/thinbridge_ros2_side.py"
docker ps --format '{{.Names}}' | grep -q '^s4_adapter$' || \
  docker run -d --network host --name s4_adapter \
    -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
    -v "$DIRB":/exp:ro "$JAZZY_IMG" bash -lc "python3 /exp/trajectory_to_intent_stage4.py"

sed -i 's/strategy: frontier_lite/strategy: external/' "$YAML"
for i in $(seq 1 "$N"); do
  echo "===== C 续跑轮 $i/$N $(date +%H:%M:%S)(每轮 ~6 分钟,RViz 地图持续累积) ====="
  cd "$CLEAN/orchestration/sim" || exit 9
  go run ./cmd/navlab-sim run exploration --live-preflight > /home/ai4s/gui_c_loop.log 2>&1 &
  RUN_PID=$!
  sleep 30
  docker run --rm --network host -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" "$JAZZY_IMG" \
    bash -lc "timeout 5 ros2 topic pub /gbp/enable std_msgs/msg/Bool '{data: true}' -r 2 >/dev/null 2>&1" || true
  E "timeout 10 rosservice call /planner_control_interface/std_srvs/automatic_planning '{}' 2>&1 | head -1" || true
  wait $RUN_PID
  echo "----- 轮 $i 结束(结果无所谓,演示看画面) -----"
done
restore_yaml
echo "===== 循环演示结束($N 轮),配置已还原 ====="
