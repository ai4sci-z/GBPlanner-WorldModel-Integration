#!/usr/bin/env bash
# 阶段2j·正式验收(rclpy 订阅版;stage2i 已证明 CLI echo 对 rclpy 发布者收不到是工具坑):
#   fresh 仿真 -> 双端桥 -> rclpy 长驻订阅先就位 -> 起飞+触发 -> 统计收到条数。
set -u
DIR=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/gbplanner_ref
BR=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/integration/ros1_bridge
OUT=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/stage2j_evidence.txt
JAZZY_IMG=navlab/official-baseline:jazzy-latest
URI='<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'
E() { docker exec gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; $1"; }

{
echo "=== STAGE2J START $(date) ==="
echo "--- 0. fresh 仿真 + 双端桥 + rclpy 订阅先就位 ---"
docker rm -f thin_ros2 s2j_sub >/dev/null 2>&1 || true
bash "$DIR/run_light_hostnet.sh"
sleep 45
docker cp "$BR/thinbridge_ros1_side.py" gbplanner_ref:/tmp/thinbridge_ros1_side.py
docker exec -d gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; python3 /tmp/thinbridge_ros1_side.py > /tmp/thinbridge_ros1.log 2>&1"
sleep 4
docker run -d --network host --name thin_ros2 \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  -v "$BR":/exp:ro "$JAZZY_IMG" bash -lc "python3 /exp/thinbridge_ros2_side.py"
docker run -d --network host --name s2j_sub \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  -v "$BR":/exp:ro "$JAZZY_IMG" bash -lc "timeout 170 python3 /exp/sub_test_traj.py; sleep 600"
sleep 10

echo "--- 1. 起飞 + 触发探索 ---"
bash "$DIR/takeoff_and_explore.sh" 2>&1 | grep -E "success|z:" | head -6

echo "--- 2. 观察 100s ---"
sleep 100

echo "--- 3. 验收 ---"
docker logs s2j_sub 2>&1 | tail -3
N=$(docker logs s2j_sub 2>&1 | grep -oE "RESULT count=[0-9]+" | grep -oE "[0-9]+" | tail -1)
echo "[ros1端] "; E "grep -c 'traj -> tcp' /tmp/thinbridge_ros1.log"; E "tail -2 /tmp/thinbridge_ros1.log"
echo "[ros2端] "; docker logs thin_ros2 2>&1 | grep -E "traj ->|lost|failed" | tail -5
if [ -n "$N" ] && [ "$N" -ge 2 ]; then echo "STAGE2=PASS (rclpy subscriber received $N trajectories)"; else echo "STAGE2=FAIL (N=$N)"; fi

docker rm -f s2j_sub >/dev/null 2>&1 || true
echo "=== STAGE2J END $(date) ==="
} 2>&1 | tee "$OUT"
