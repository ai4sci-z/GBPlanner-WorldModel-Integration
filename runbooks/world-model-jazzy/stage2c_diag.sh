#!/usr/bin/env bash
# 阶段2c 诊断:①zenoh 会话是否建立 ②rosrust 订 rospy 发布者是否也失败(定性兼容坑)
set -u
OUT=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/stage2c_evidence.txt
E() { docker exec gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; $1"; }

{
echo "=== STAGE2C DIAG START $(date) ==="

echo "--- 1. docker hub tags(zenoh-bridge-ros1) ---"
python3 /mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/stage2c_diag.py

echo "--- 2. 两桥 zenoh 会话证据(logs 里 transport/session/link) ---"
docker logs z_ros1 2>&1 | grep -iE "transport|session|link|new.*peer|established|connect" | head -6 || echo "(z_ros1 no session lines)"
docker logs z_ros2dds 2>&1 | grep -iE "transport|session|link|new.*peer|established|connect" | head -6 || echo "(z_ros2dds no session lines)"

echo "--- 3. rosrust 订 rospy(rostopic pub) 发布者:能通吗 ---"
E "nohup timeout 60 rostopic pub /diag_rospy std_msgs/String 'data: hello_from_rospy' -r 2 >/dev/null 2>&1 &"
sleep 3
BEFORE=$(docker logs z_ros1 2>&1 | wc -l)
sleep 12
docker logs z_ros1 2>&1 | tail -n +$BEFORE | grep -iE "diag_rospy|mismatch|error" | head -6 || echo "(no new errors about /diag_rospy)"

echo "--- 4. jazzy 侧能否收到 /diag_rospy(判定 rospy 路是否全通,40s) ---"
URI='<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'
docker run --rm --network host \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  navlab/official-baseline:jazzy-latest bash -lc "timeout 40 ros2 topic echo /diag_rospy --once 2>&1 | head -4; echo ECHO_DONE"

echo "--- 5. ros1 桥完整错误样本(头一条,含未截断字段) ---"
docker logs z_ros1 2>&1 | grep -B1 -A3 "mismatched" | head -12

echo "=== STAGE2C DIAG END $(date) ==="
} 2>&1 | tee "$OUT"
