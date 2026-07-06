#!/usr/bin/env bash
# 阶段2h·分辨"发布了却收不到":
#   A) 新容器 echo(全文) + B) 新容器 echo --field,双听 /gbp/trajectory
#   C) 在 thin_ros2 同容器同环境 exec 发布 5 条测试 trajectory
#   若 A/B 收到 C 的->DDS 通,thin_ros2 主进程的发布有问题;都收不到->环境/QoS 实锤。
set -u
OUT=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/stage2h_evidence.txt
JAZZY_IMG=navlab/official-baseline:jazzy-latest
URI='<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'

{
echo "=== STAGE2H START $(date) ==="
docker rm -f s2h_echo_full s2h_echo_field >/dev/null 2>&1 || true

echo "--- 0. thin_ros2 还活着吗 ---"
docker ps --format "{{.Names}}" | grep -c thin_ros2 || echo "THIN_ROS2_GONE"

echo "--- 1. 双订阅就位 ---"
docker run -d --network host --name s2h_echo_full \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  "$JAZZY_IMG" bash -lc "ros2 topic echo /gbp/trajectory"
docker run -d --network host --name s2h_echo_field \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  "$JAZZY_IMG" bash -lc "ros2 topic echo /gbp/trajectory --field header.frame_id"
sleep 8

echo "--- 2. thin_ros2 容器内 exec 发布 5 条测试 traj ---"
# 注意:docker exec 不经过 /ros_entrypoint.sh,必须显式 source
docker exec thin_ros2 bash -c "source /opt/ros/jazzy/setup.bash && timeout 15 python3 /exp/pub_test_traj.py"

sleep 3
echo "--- 3. 判定 ---"
NF=$(docker logs s2h_echo_full 2>&1 | grep -c "frame_id: map")
NB=$(docker logs s2h_echo_field 2>&1 | grep -c "^map")
echo "full_echo received=$NF  field_echo received=$NB"
docker logs s2h_echo_full 2>&1 | head -6
echo "  ----"
docker logs s2h_echo_field 2>&1 | head -4

echo "--- 4. 顺带:thin_ros2 主进程当前 stats 与错误 ---"
docker logs thin_ros2 2>&1 | grep -E "stats|error|lost|connected" | tail -5

docker rm -f s2h_echo_full s2h_echo_field >/dev/null 2>&1 || true
echo "=== STAGE2H END $(date) ==="
} 2>&1 | tee "$OUT"
