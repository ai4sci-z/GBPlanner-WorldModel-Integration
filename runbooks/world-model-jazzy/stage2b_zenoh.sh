#!/usr/bin/env bash
# 阶段2b·zenoh 双桥冒烟(不接飞控):
#   gbplanner_ref(hostnet ROS1) <-> zenoh-bridge-ros1 <-> tcp:7447 <-> zenoh-bridge-ros2dds <-> jazzy(DDS)
# 验收:①jazzy 侧看到并收到 ROS1 的 odometry ②ROS1 侧收到 jazzy 发的话题 ③trajectory 冒烟。
set -u
DIR=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/gbplanner_ref
OUT=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/stage2b_evidence.txt
JAZZY_IMG=navlab/official-baseline:jazzy-latest
URI='<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'
E() { docker exec gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; $1"; }

{
echo "=== STAGE2B START $(date) ==="
echo "--- 0. 清场并起 gbplanner(hostnet 版) ---"
docker rm -f z_ros1 z_ros2dds s2b_jpub >/dev/null 2>&1 || true
bash "$DIR/run_light_hostnet.sh"
sleep 35
E "rosnode list" | head -5

echo "--- 1. 起 zenoh-bridge-ros1(连 ROS1 master,listen tcp:7447) ---"
docker run -d --network host --name z_ros1 eclipse/zenoh-bridge-ros1:latest \
  --ros_master_uri http://localhost:11311/ --ros_hostname localhost \
  -m peer -l tcp/127.0.0.1:7447 --no-multicast-scouting
sleep 5
docker logs z_ros1 2>&1 | tail -5

echo "--- 2. 起 zenoh-bridge-ros2dds(connect tcp:7447,DDS domain 0) ---"
docker run -d --network host --name z_ros2dds \
  -e CYCLONEDDS_URI="$URI" \
  eclipse/zenoh-bridge-ros2dds:latest \
  peer -e tcp/127.0.0.1:7447 -d 0 --no-multicast-scouting
sleep 8
docker logs z_ros2dds 2>&1 | tail -5

echo "--- 3. ROS1->ROS2:jazzy 侧话题列表(应见 /rmf_obelix/*) ---"
docker run --rm --network host \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  "$JAZZY_IMG" bash -lc "timeout 30 ros2 topic list 2>/dev/null | grep -E 'rmf|odometry' | head -10"

echo "--- 4. ROS1->ROS2:jazzy 收 odometry_throttled(--once,最长 60s) ---"
docker run --rm --network host \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  "$JAZZY_IMG" bash -lc "timeout 60 ros2 topic echo /rmf_obelix/ground_truth/odometry_throttled --once 2>&1 | head -12"
echo "R1TO2_RC=$?"

echo "--- 5. ROS2->ROS1:jazzy 发 String,ROS1 侧收 ---"
docker run -d --rm --network host --name s2b_jpub \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  "$JAZZY_IMG" bash -lc "ros2 topic pub /bridge_r2to1 std_msgs/msg/String 'data: hello_ros1' -r 2"
sleep 8
E "timeout 30 rostopic echo -n1 /bridge_r2to1 2>&1 | head -3"
echo "R2TO1_RC=$?"
docker rm -f s2b_jpub >/dev/null 2>&1 || true

echo "--- 6. trajectory 冒烟:起飞+触发探索,jazzy 侧收 trajectory(--once,最长 90s) ---"
bash "$DIR/takeoff_and_explore.sh" >/dev/null 2>&1 &
docker run --rm --network host \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  "$JAZZY_IMG" bash -lc "timeout 90 ros2 topic echo /rmf_obelix/command/trajectory --once 2>&1 | head -20"
echo "TRAJ_RC=$?"
wait

echo "--- 7. 桥日志尾部(排障用) ---"
docker logs z_ros1 2>&1 | tail -8
echo "  ----"
docker logs z_ros2dds 2>&1 | tail -8

echo "=== STAGE2B END $(date) ==="
} 2>&1 | tee "$OUT"
