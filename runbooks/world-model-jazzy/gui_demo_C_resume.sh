#!/usr/bin/env bash
# GUI-C·续跑(只补数据源):不重启 planner/不清体素图/不动任何已有窗口,
# 只起一轮 world-model live run 喂桥 → 现有 RViz 里地图继续生长,Start Planner 有反应。
# 前提:gbplanner_ref(含 thinbridge)/thin_ros2/s4_adapter 已在跑(gui_demo_master 起过)。
set -o pipefail
export PATH=/usr/local/go/bin:$PATH
export NAVLAB_SIM_DISTRO=jazzy
CLEAN=/home/ai4s/ws-clean/world-model
YAML=$CLEAN/orchestration/sim/configs/tasks/exploration.yaml
JAZZY_IMG=navlab/official-baseline:jazzy-latest
URI='<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'
E() { docker exec gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; $1"; }
restore_yaml() { sed -i 's/strategy: external/strategy: frontier_lite/' "$YAML"; }
trap restore_yaml EXIT

for c in gbplanner_ref thin_ros2 s4_adapter; do
  docker ps --format '{{.Names}}' | grep -q "^$c$" || { echo "缺 $c——请先跑 gui_demo_master.sh"; exit 1; }
done
docker exec gbplanner_ref bash -c 'pgrep -f thinbridge_ros1 >/dev/null' || {
  echo "桥 ROS1 侧不在,补拉起";
  docker exec -d gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; python3 /tmp/thinbridge_ros1_side.py > /tmp/thinbridge_ros1.log 2>&1"; }

echo "=== live run 起(external;喂桥约 6 分钟)==="
sed -i 's/strategy: frontier_lite/strategy: external/' "$YAML"
cd "$CLEAN/orchestration/sim" || exit 9
go run ./cmd/navlab-sim run exploration --live-preflight > /home/ai4s/gui_c_resume.log 2>&1 &
RUN_PID=$!
sleep 30
docker run --rm --network host -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" "$JAZZY_IMG" \
  bash -lc "timeout 5 ros2 topic pub /gbp/enable std_msgs/msg/Bool '{data: true}' -r 2 >/dev/null 2>&1; echo enabled"
E "timeout 10 rosservice call /planner_control_interface/std_srvs/automatic_planning '{}' 2>&1 | head -2"
echo ">>> 现在看 RViz:1~2 分钟内点云/体素继续生长;此期间点 Start Planner 会有反应 <<<"
wait $RUN_PID
tail -2 /home/ai4s/gui_c_resume.log
restore_yaml
echo "=== 本轮结束(约 6 分钟);想再看再跑本脚本 ==="
