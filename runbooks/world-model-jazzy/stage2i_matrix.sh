#!/usr/bin/env bash
# 阶段2i·rclpy pub -> {CLI echo, rclpy sub} 对照矩阵 + 首条到达时间。
# 发布 60 条(60s),两种订阅先就位,判定是慢发现还是彻底不通。
set -u
OUT=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/stage2i_evidence.txt
BR=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/integration/ros1_bridge
JAZZY_IMG=navlab/official-baseline:jazzy-latest
URI='<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'

{
echo "=== STAGE2I START $(date) ==="
docker rm -f s2i_echo s2i_rclpy s2i_pub >/dev/null 2>&1 || true

echo "--- 1. 两种订阅先就位 ---"
docker run -d --network host --name s2i_echo \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  "$JAZZY_IMG" bash -lc "ros2 topic echo /gbp/trajectory --field header.frame_id"
docker run -d --network host --name s2i_rclpy \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  -v "$BR":/exp:ro "$JAZZY_IMG" bash -lc "python3 /exp/sub_test_traj.py"
sleep 8

echo "--- 2. rclpy 发布 60 条(独立容器) ---"
docker run --rm --network host --name s2i_pub \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  -v "$BR":/exp:ro "$JAZZY_IMG" bash -lc "timeout 70 python3 /exp/pub_test_traj.py 60"

sleep 3
echo "--- 3. 判定 ---"
NE=$(docker logs s2i_echo 2>&1 | grep -c "^map")
echo "CLI_echo received=$NE"
echo "[rclpy_sub 输出] "; docker logs s2i_rclpy 2>&1 | tail -3

docker rm -f s2i_echo s2i_rclpy >/dev/null 2>&1 || true
echo "=== STAGE2I END $(date) ==="
} 2>&1 | tee "$OUT"
