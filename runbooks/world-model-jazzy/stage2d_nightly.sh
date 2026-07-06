#!/usr/bin/env bash
# 阶段2d:zenoh-bridge-ros1 换 nightly tag 重试(最后一次机会,失败转自写薄桥)。
# 判定不再用管道 RC(上次假阳性),按输出内容判定。
set -u
OUT=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/stage2d_evidence.txt
JAZZY_IMG=navlab/official-baseline:jazzy-latest
URI='<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'
E() { docker exec gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; $1"; }

{
echo "=== STAGE2D START $(date) ==="
echo "--- 0. 拉 nightly + 清旧桥 ---"
docker pull eclipse/zenoh-bridge-ros1:nightly 2>&1 | tail -1
docker rm -f z_ros1 z_ros2dds >/dev/null 2>&1 || true

echo "--- 1. 起 nightly ros1 桥 ---"
docker run -d --network host --name z_ros1 eclipse/zenoh-bridge-ros1:nightly \
  --ros_master_uri http://localhost:11311/ --ros_hostname localhost \
  -m peer -l tcp/127.0.0.1:7447 --no-multicast-scouting
sleep 6
echo "[版本] $(docker logs z_ros1 2>&1 | grep -oE 'zenoh-bridge-ros1 v[^ ]+' | head -1)"
echo "[mismatch错误数] $(docker logs z_ros1 2>&1 | grep -c mismatched)"

echo "--- 2. 起 ros2dds 桥 ---"
docker run -d --network host --name z_ros2dds -e CYCLONEDDS_URI="$URI" -e ROS_DISTRO=jazzy \
  eclipse/zenoh-bridge-ros2dds:latest peer -e tcp/127.0.0.1:7447 -d 0 --no-multicast-scouting
sleep 10

echo "--- 3. jazzy 侧话题列表(找 rmf) ---"
docker run --rm --network host \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  "$JAZZY_IMG" bash -lc "timeout 30 ros2 topic list 2>/dev/null" > /tmp/s2d_topics.txt
grep -cE "rmf" /tmp/s2d_topics.txt && echo "RMF_TOPICS_VISIBLE" || echo "NO_RMF_TOPICS"
grep -E "rmf" /tmp/s2d_topics.txt | head -8

echo "--- 4. jazzy 收 odometry_throttled(60s,按内容判定) ---"
docker run --rm --network host \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  "$JAZZY_IMG" bash -lc "timeout 60 ros2 topic echo /rmf_obelix/ground_truth/odometry_throttled --once 2>&1" > /tmp/s2d_odom.txt
if grep -q "position" /tmp/s2d_odom.txt; then echo "R1TO2=SUCCESS"; head -14 /tmp/s2d_odom.txt; else echo "R1TO2=FAIL"; tail -3 /tmp/s2d_odom.txt; fi

echo "--- 5. ROS2->ROS1(40s,按内容判定) ---"
docker rm -f s2d_jpub >/dev/null 2>&1 || true
docker run -d --rm --network host --name s2d_jpub \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  "$JAZZY_IMG" bash -lc "ros2 topic pub /bridge_r2to1 std_msgs/msg/String 'data: hello_ros1' -r 2"
sleep 8
E "timeout 30 rostopic echo -n1 /bridge_r2to1 2>&1" > /tmp/s2d_r2to1.txt
if grep -q "hello_ros1" /tmp/s2d_r2to1.txt; then echo "R2TO1=SUCCESS"; else echo "R2TO1=FAIL"; head -3 /tmp/s2d_r2to1.txt; fi
docker rm -f s2d_jpub >/dev/null 2>&1 || true

echo "--- 6. nightly 桥日志尾部 ---"
docker logs z_ros1 2>&1 | tail -6

echo "=== STAGE2D END $(date) ==="
} 2>&1 | tee "$OUT"
