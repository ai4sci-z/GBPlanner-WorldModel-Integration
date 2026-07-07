#!/bin/bash
# GUI-A 临门一脚(预研B takeoff_and_explore 的 gbplanner_orig 版):起飞→自主探索
set -u
E() { docker exec gbplanner_orig bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311; export ROS_HOSTNAME=localhost; $1"; }
echo "== 升高到 z=1.2 =="
E "timeout 8 rostopic pub -1 /rmf_obelix/command/pose geometry_msgs/PoseStamped '{header: {frame_id: world}, pose: {position: {x: 0.0, y: 0.0, z: 1.2}, orientation: {w: 1.0}}}' 2>&1 | tail -1"
E "sleep 8"
echo "== 触发自主探索 =="
E "timeout 10 rosservice call /planner_control_interface/std_srvs/automatic_planning '{}' 2>&1 | head -3"
echo "== 完成:看 RViz——飞机开始自主巡飞、地图增长、轨迹延伸 =="
