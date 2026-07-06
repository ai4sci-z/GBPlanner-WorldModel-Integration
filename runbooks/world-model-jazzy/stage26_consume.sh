#!/usr/bin/env bash
# 阶段2.6·GBPlanner 真消费 /wm/* 验收(Review_008 分界线):
#   纯 planner 栈(wm_planner.launch,无 gazebo/RotorS)+ 薄桥 + jazzy 手工 odom/scan。
# 分级验收:a) rostopic info 消费关系  b) voxblox 建图心跳(消费点云)
#          c) 触发规划 -> trajectory(2D 冒烟输入下可能拒,如实记录)
set -u
BR=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/integration/ros1_bridge
OUT=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/stage26_evidence.txt
JAZZY_IMG=navlab/official-baseline:jazzy-latest
URI='<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'
E() { docker exec gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; $1"; }
JRUN_D() { docker run -d --rm --network host --name "$1" -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" "$JAZZY_IMG" bash -lc "$2"; }

{
echo "=== STAGE26 START $(date) ==="
echo "--- 0. 起纯 planner 栈(无 gazebo)+ 薄桥两端 ---"
docker rm -f gbplanner_ref thin_ros2 s26_opub s26_spub s26_sub >/dev/null 2>&1 || true
docker run -d --network host \
  -e ROS_HOSTNAME=localhost -e ROS_MASTER_URI=http://localhost:11311 -e ROS_IP=127.0.0.1 \
  -e PYTHONUNBUFFERED=1 \
  --name gbplanner_ref gbplanner-ref:latest \
  bash -c 'source /opt/ros/noetic/setup.bash && source /root/gbp_ws/devel/setup.bash && sleep 2 && roslaunch /root/wm_planner.launch 2>&1'
sleep 5
docker cp "$BR/wm_planner.launch" gbplanner_ref:/root/wm_planner.launch
docker restart gbplanner_ref >/dev/null
sleep 25
E "rosnode list" | head -8

docker cp "$BR/thinbridge_ros1_side.py" gbplanner_ref:/tmp/thinbridge_ros1_side.py
docker exec -d gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; python3 /tmp/thinbridge_ros1_side.py > /tmp/thinbridge_ros1.log 2>&1"
sleep 4
docker run -d --network host --name thin_ros2 \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  -v "$BR":/exp:ro "$JAZZY_IMG" bash -lc "python3 /exp/thinbridge_ros2_side.py"
sleep 5

echo "--- 1. jazzy 手工发 odom(z=1,10Hz)+ scan(带开口几何,5Hz) ---"
JRUN_D s26_opub "ros2 topic pub /slam/odom nav_msgs/msg/Odometry '{header: {frame_id: map}, child_frame_id: base_link, pose: {pose: {position: {x: 0.0, y: 0.0, z: 1.0}, orientation: {w: 1.0}}}}' -r 10"
JRUN_D s26_spub "ros2 topic pub /scan sensor_msgs/msg/LaserScan '{header: {frame_id: base_scan}, angle_min: -3.14, angle_max: 3.14, angle_increment: 0.393, range_min: 0.1, range_max: 12.0, ranges: [6,6,6,.inf,.inf,6,6,6,6,.inf,.inf,6,6,6,6,6,6]}' -r 5"
sleep 12

echo "--- 2. [验收a] 消费关系:/wm/* 的 Subscribers 应含 gbplanner_node/pci ---"
E "timeout 8 rostopic info /wm/odom 2>&1 | head -8"
E "timeout 8 rostopic info /wm/points 2>&1 | head -8"

echo "--- 3. [验收b] voxblox 建图心跳(消费 /wm/points 的证据) ---"
E "timeout 12 rostopic hz /gbplanner_node/tsdf_pointcloud 2>&1 | grep -E 'average|no new' | head -1"
E "timeout 8 rostopic echo -n1 /gbplanner_node/tsdf_pointcloud/header 2>/dev/null | head -5"

echo "--- 4. [验收c] 触发规划 -> trajectory(2D 冒烟输入,拒了如实记录) ---"
docker run -d --rm --network host --name s26_sub \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  -v "$BR":/exp:ro "$JAZZY_IMG" bash -lc "timeout 80 python3 /exp/sub_test_traj.py; sleep 300"
sleep 8
E "timeout 10 rosservice call /planner_control_interface/std_srvs/automatic_planning '{}' 2>&1 | head -3"
sleep 60
docker logs s26_sub 2>&1 | tail -3

echo "--- 5. 两端桥统计与 planner 日志尾部 ---"
E "tail -4 /tmp/thinbridge_ros1.log"
docker logs thin_ros2 2>&1 | grep -E "stats|traj" | tail -4
docker logs gbplanner_ref 2>&1 | grep -iE "error|warn|plan" | tail -8

docker rm -f s26_opub s26_spub s26_sub >/dev/null 2>&1 || true
echo "=== STAGE26 END $(date) ==="
} 2>&1 | tee "$OUT"
