#!/usr/bin/env bash
# 阶段2f·薄桥完整同框验收:fresh gbplanner 仿真 + 双端桥 + 起飞 + 触发探索
#   -> jazzy 侧收 /gbp/trajectory(A/B 已在 2e 通过,本轮主验 C)。
set -u
DIR=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/gbplanner_ref
BR=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/integration/ros1_bridge
OUT=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/stage2f_evidence.txt
JAZZY_IMG=navlab/official-baseline:jazzy-latest
URI='<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'
E() { docker exec gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; $1"; }

{
echo "=== STAGE2F START $(date) ==="
echo "--- 0. fresh 仿真 + 双端桥 ---"
docker rm -f thin_ros2 >/dev/null 2>&1 || true
bash "$DIR/run_light_hostnet.sh"
sleep 45
E "rosnode list | head -5"
docker cp "$BR/thinbridge_ros1_side.py" gbplanner_ref:/tmp/thinbridge_ros1_side.py
docker exec -d gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; python3 /tmp/thinbridge_ros1_side.py > /tmp/thinbridge_ros1.log 2>&1"
sleep 4
docker run -d --network host --name thin_ros2 \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  -v "$BR":/exp:ro "$JAZZY_IMG" bash -lc "python3 /exp/thinbridge_ros2_side.py"
sleep 5

echo "--- 1. 起飞 + 触发探索 ---"
bash "$DIR/takeoff_and_explore.sh" 2>&1 | grep -E "=====|success|z:" | head -12

echo "--- 2. jazzy 收 /gbp/trajectory(120s,按内容判定) ---"
docker run --rm --network host \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  "$JAZZY_IMG" bash -lc "timeout 120 ros2 topic echo /gbp/trajectory --once 2>&1" > /tmp/s2f_c.txt
if grep -q "translation" /tmp/s2f_c.txt; then
  echo "C_TRAJ=SUCCESS"
  grep -c "translation" /tmp/s2f_c.txt | sed "s/^/  waypoints=/"
  sed -n "1,16p" /tmp/s2f_c.txt
else
  echo "C_TRAJ=FAIL"; head -5 /tmp/s2f_c.txt
fi

echo "--- 3. 桥两侧统计 ---"
E "tail -4 /tmp/thinbridge_ros1.log"
docker logs thin_ros2 2>&1 | tail -4

echo "=== STAGE2F END $(date) ==="
} 2>&1 | tee "$OUT"
