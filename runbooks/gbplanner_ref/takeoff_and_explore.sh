#!/bin/bash
# 临门一脚:让 rmf_obelix 起飞,再触发 GBPlanner 自主探索
set -u
E() { docker exec gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311; export ROS_HOSTNAME=localhost; $1"; }

echo "===== 0. 起飞前高度 ====="
E "timeout 5 rostopic echo -n1 /rmf_obelix/ground_truth/odometry_throttled/pose/pose/position 2>/dev/null | head -4"

echo "===== 1. 向 lee 控制器发升高位姿(z=1.2) ====="
E "timeout 8 rostopic pub -1 /rmf_obelix/command/pose geometry_msgs/PoseStamped '{header: {frame_id: world}, pose: {position: {x: 0.0, y: 0.0, z: 1.2}, orientation: {w: 1.0}}}' 2>&1 | tail -1"

echo "===== 2. 等 8 秒,看高度 ====="
E "sleep 8; timeout 5 rostopic echo -n1 /rmf_obelix/ground_truth/odometry_throttled/pose/pose/position 2>/dev/null | head -4"

echo "===== 3. 触发自主探索(automatic_planning) ====="
E "timeout 10 rosservice call /planner_control_interface/std_srvs/automatic_planning '{}' 2>&1 | head -3"

echo "===== 4. 10 秒后:出轨迹了吗 + 位置动了吗 ====="
E "sleep 10; echo '--- command/trajectory: '; timeout 5 rostopic hz /rmf_obelix/command/trajectory 2>&1 | grep -E 'average|no new' | head -1; echo '--- 当前位置: '; timeout 5 rostopic echo -n1 /rmf_obelix/ground_truth/odometry_throttled/pose/pose/position 2>/dev/null | head -4"
