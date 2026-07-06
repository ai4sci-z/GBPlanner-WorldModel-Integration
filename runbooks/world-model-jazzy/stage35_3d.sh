#!/usr/bin/env bash
# 阶段3.5·3D 联跑(史诗同框):world-model 真栈(真odom+真3D点云) <-薄桥-> ROS1 纯 planner 栈。
# 验收:a)cloud3d 过桥 b)voxblox tsdf z 分布=3D(判据②) c)trajectory z 变化(判据③)。
set -o pipefail
export PATH=/usr/local/go/bin:$PATH
export NAVLAB_SIM_DISTRO=jazzy
CLEAN=/home/ai4s/ws-clean/world-model
DIRB=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/integration/ros1_bridge
OUT=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/stage35_evidence.txt
JAZZY_IMG=navlab/official-baseline:jazzy-latest
URI='<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'
E() { docker exec gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; $1"; }

{
echo "=== STAGE35 3D START $(date) ==="
echo "--- 0. fresh ROS1 纯 planner 栈 + 薄桥两端(cloud3d 直通版)---"
docker rm -f thin_ros2 s35_sub >/dev/null 2>&1 || true
docker cp "$DIRB/wm_planner.launch" gbplanner_ref:/root/wm_planner.launch
docker cp "$DIRB/thinbridge_ros1_side.py" gbplanner_ref:/tmp/thinbridge_ros1_side.py
docker cp "$DIRB/ros1_cloud_z.py" gbplanner_ref:/tmp/ros1_cloud_z.py
docker restart gbplanner_ref >/dev/null
sleep 25
E "rosnode list | head -4"
docker exec -d gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; python3 /tmp/thinbridge_ros1_side.py > /tmp/thinbridge_ros1.log 2>&1"
sleep 3
docker run -d --network host --name thin_ros2 \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  -v "$DIRB":/exp:ro "$JAZZY_IMG" bash -lc "python3 /exp/thinbridge_ros2_side.py"
docker run -d --network host --name s35_sub \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  -v "$DIRB":/exp:ro "$JAZZY_IMG" bash -lc "timeout 200 python3 /exp/sub_traj_z.py; sleep 600"
sleep 5

echo "--- 1. 起 world-model 真栈(真 odom + 真 3D 点云源)---"
cd "$CLEAN/orchestration/sim" || exit 9
go run ./cmd/navlab-sim run exploration --live-preflight > /home/ai4s/s35_run.log 2>&1 &
RUN_PID=$!
sleep 45

echo "--- 2. 中场检查:cloud3d 过桥了吗 ---"
E "grep -oE 'cloud3d_in.: [0-9]+' /tmp/thinbridge_ros1.log | tail -1 || true"
docker logs thin_ros2 2>&1 | grep -E "stats" | tail -1

echo "--- 3. 触发规划 ---"
E "timeout 10 rosservice call /planner_control_interface/std_srvs/automatic_planning '{}' 2>&1 | head -2"
sleep 30

echo "--- 4. [判据②] voxblox tsdf z 分布 ---"
E "timeout 40 python3 /tmp/ros1_cloud_z.py /gbplanner_node/tsdf_pointcloud 35"

echo "--- 5. [判据③] trajectory z 变化 ---"
docker logs s35_sub 2>&1 | grep -E "TRAJ#|RESULT" | tail -6

echo "--- 6. 两端统计 ---"
E "tail -3 /tmp/thinbridge_ros1.log"
docker logs thin_ros2 2>&1 | grep stats | tail -2

echo "--- 7. 等 world-model run 结束 ---"
wait $RUN_PID
tail -3 /home/ai4s/s35_run.log
echo "=== STAGE35 3D END $(date) ==="
} 2>&1 | tee "$OUT"
