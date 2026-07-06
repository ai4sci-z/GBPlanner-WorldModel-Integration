#!/usr/bin/env bash
# 阶段2e·自写薄桥冒烟(zenoh 判死后的 B2.5 方案):
#   gbplanner_ref(ROS1) <-tcp:7601-> jazzy 容器(ROS2)
# 验收:A) ROS2 手工 odom -> ROS1 /wm/odom  B) ROS2 手工 scan -> ROS1 /wm/points
#      C) 触发探索 -> jazzy 收 /gbp/trajectory
set -u
BR=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/integration/ros1_bridge
OUT=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/stage2e_evidence.txt
JAZZY_IMG=navlab/official-baseline:jazzy-latest
URI='<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'
E() { docker exec gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; $1"; }
JRUN_D() { docker run -d --rm --network host --name "$1" -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" "$JAZZY_IMG" bash -lc "$2"; }

{
echo "=== STAGE2E START $(date) ==="
echo "--- 0. 清 zenoh 桥,部署薄桥两端 ---"
docker rm -f z_ros1 z_ros2dds thin_ros2 s2e_opub s2e_spub >/dev/null 2>&1 || true
docker exec gbplanner_ref bash -c "pkill -f thinbridge_ros1_side || true"
docker cp "$BR/thinbridge_ros1_side.py" gbplanner_ref:/tmp/thinbridge_ros1_side.py
docker exec -d gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; python3 /tmp/thinbridge_ros1_side.py > /tmp/thinbridge_ros1.log 2>&1"
sleep 4
docker run -d --network host --name thin_ros2 \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  -v "$BR":/exp:ro "$JAZZY_IMG" bash -lc "python3 /exp/thinbridge_ros2_side.py"
sleep 6
echo "[ros1端日志头] "; E "head -4 /tmp/thinbridge_ros1.log"
echo "[ros2端日志头] "; docker logs thin_ros2 2>&1 | head -4

echo "--- A. ROS2->ROS1 odom ---"
JRUN_D s2e_opub "ros2 topic pub /slam/odom nav_msgs/msg/Odometry '{header: {frame_id: map}, child_frame_id: base_link, pose: {pose: {position: {x: 1.5, y: 2.5, z: 0.8}, orientation: {w: 1.0}}}}' -r 5"
sleep 6
E "timeout 20 rostopic echo -n1 /wm/odom 2>&1" > /tmp/s2e_a.txt
if grep -q "x: 1.5" /tmp/s2e_a.txt; then echo "A_ODOM=SUCCESS"; grep -A3 position /tmp/s2e_a.txt | head -4; else echo "A_ODOM=FAIL"; head -5 /tmp/s2e_a.txt; fi
docker rm -f s2e_opub >/dev/null 2>&1 || true

echo "--- B. ROS2->ROS1 scan->cloud ---"
JRUN_D s2e_spub "ros2 topic pub /scan sensor_msgs/msg/LaserScan '{header: {frame_id: base_scan}, angle_min: 0.0, angle_max: 0.2, angle_increment: 0.1, range_min: 0.1, range_max: 10.0, ranges: [1.0, 2.0, 3.0]}' -r 5"
sleep 6
E "timeout 20 rostopic echo -n1 /wm/points 2>&1 | head -18" > /tmp/s2e_b.txt
if grep -q "width: 3" /tmp/s2e_b.txt; then echo "B_CLOUD=SUCCESS (width=3)"; grep -E "frame_id|width|height" /tmp/s2e_b.txt; else echo "B_CLOUD=FAIL"; head -6 /tmp/s2e_b.txt; fi
docker rm -f s2e_spub >/dev/null 2>&1 || true

echo "--- C. ROS1->ROS2 trajectory(重触发探索,90s 内收) ---"
E "timeout 10 rosservice call /planner_control_interface/std_srvs/automatic_planning '{}' 2>&1 | head -2"
docker run --rm --network host \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  "$JAZZY_IMG" bash -lc "timeout 90 ros2 topic echo /gbp/trajectory --once 2>&1" > /tmp/s2e_c.txt
if grep -q "translation" /tmp/s2e_c.txt; then echo "C_TRAJ=SUCCESS"; grep -B2 -A4 "translation" /tmp/s2e_c.txt | head -12; else echo "C_TRAJ=FAIL"; head -5 /tmp/s2e_c.txt; fi

echo "--- 桥两侧日志尾部 ---"
E "tail -6 /tmp/thinbridge_ros1.log"
docker logs thin_ros2 2>&1 | tail -6

echo "=== STAGE2E END $(date) ==="
} 2>&1 | tee "$OUT"
