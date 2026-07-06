#!/usr/bin/env bash
# 阶段1·gbplanner-ref 单侧复验(不碰 world-model):
# 起仿真 -> 验证节点/建图 -> 起飞 -> 触发探索 -> 抓 command/trajectory 实测证据(含 frame_id)。
set -u
DIR=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/gbplanner_ref
OUT=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/stage1_evidence.txt
E() { docker exec gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; $1"; }

{
echo "=== STAGE1 START $(date) ==="
echo "--- 1. run_light.sh 起仿真 ---"
bash "$DIR/run_light.sh"
sleep 35

echo "--- 2. 节点清单(应有 gbplanner_node + pci) ---"
E "rosnode list" | grep -E "gbplanner|pci|voxblox" || echo "NODES_MISSING"

echo "--- 3. voxblox 建图心跳(tsdf_pointcloud hz) ---"
E "timeout 8 rostopic hz /gbplanner_node/tsdf_pointcloud 2>&1 | grep -E 'average|no new' | head -1"

echo "--- 4. 起飞 + 触发探索(takeoff_and_explore.sh) ---"
bash "$DIR/takeoff_and_explore.sh"

echo "--- 5. trajectory 证据:hz ---"
E "timeout 10 rostopic hz /rmf_obelix/command/trajectory 2>&1 | grep -E 'average|no new' | head -1"

echo "--- 6. trajectory 证据:抓一条(头 45 行,看 frame_id/首个 waypoint) ---"
E "timeout 20 rostopic echo -n1 /rmf_obelix/command/trajectory 2>/dev/null | head -45"

echo "--- 7. odometry frame 证据(桥接 TF 对照表用) ---"
E "timeout 5 rostopic echo -n1 /rmf_obelix/ground_truth/odometry_throttled/header 2>/dev/null | head -6"
E "timeout 5 rostopic echo -n1 /rmf_obelix/ground_truth/odometry_throttled/child_frame_id 2>/dev/null | head -2"

echo "--- 8. 点云输入 frame 证据 ---"
E "timeout 8 rostopic echo -n1 /rmf_obelix/velodyne_points/header 2>/dev/null | head -6"

echo "=== STAGE1 END $(date) ==="
} 2>&1 | tee "$OUT"
