#!/usr/bin/env bash
# 世界一致性核查跑(不动 gbplanner_orig / wm_gzgui):
# ①清 voxblox(restart planner)+ 新 RViz → 排旧图残留 ②TF 链取证(双侧)
# ③world↔map 恒等验证(同刻位姿对比)④体素几何 vs 迷宫 SDF 地标(墙线直方图)
set -o pipefail
export PATH=/usr/local/go/bin:$PATH
export NAVLAB_SIM_DISTRO=jazzy
CLEAN=/home/ai4s/ws-clean/world-model
DIRB=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/integration/ros1_bridge
HERE=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy
OUT=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/stage5e_worldcheck_evidence.txt
YAML=$CLEAN/orchestration/sim/configs/tasks/exploration.yaml
JAZZY_IMG=navlab/official-baseline:jazzy-latest
URI='<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'
E() { docker exec gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; $1"; }
J() { docker run --rm --network host -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" "$JAZZY_IMG" bash -lc "$1"; }
restore_yaml() { sed -i 's/strategy: external/strategy: frontier_lite/' "$YAML"; }
trap restore_yaml EXIT

{
echo "=== WORLDCHECK START $(date) ==="
echo "--- [1] 清 voxblox:restart planner(不动 orig/gzgui);新 RViz ---"
docker rm -f thin_ros2 s4_adapter gbp_rviz >/dev/null 2>&1 || true
docker restart gbplanner_ref >/dev/null
sleep 25
docker cp "$DIRB/maze_geo_probe.py" gbplanner_ref:/tmp/maze_geo_probe.py >/dev/null
docker cp "$DIRB/ros1_cloud_z.py" gbplanner_ref:/tmp/ros1_cloud_z.py >/dev/null
echo "--- [1a] 旧图残留排除:重启后 tsdf 应无消息/空 ---"
E "timeout 8 python3 /tmp/ros1_cloud_z.py /gbplanner_node/tsdf_pointcloud 6" || echo "(无 tsdf 消息=图确为空 ✓)"
docker exec -d gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; python3 /tmp/thinbridge_ros1_side.py > /tmp/thinbridge_ros1.log 2>&1"
sleep 3
docker run -d --network host --name thin_ros2 \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  -v "$DIRB":/exp:ro "$JAZZY_IMG" bash -lc "python3 /exp/thinbridge_ros2_side.py"
docker run -d --network host --name s4_adapter \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  -v "$DIRB":/exp:ro "$JAZZY_IMG" bash -lc "python3 /exp/trajectory_to_intent_stage4.py"
bash "$HERE/gui2_rviz.sh"

echo "--- [2] live run(external) ---"
sed -i 's/strategy: frontier_lite/strategy: external/' "$YAML"
cd "$CLEAN/orchestration/sim" || exit 9
go run ./cmd/navlab-sim run exploration --live-preflight > /home/ai4s/worldcheck_run.log 2>&1 &
RUN_PID=$!
sleep 30
J "timeout 5 ros2 topic pub /gbp/enable std_msgs/msg/Bool '{data: true}' -r 2 >/dev/null 2>&1; echo enabled"
E "timeout 10 rosservice call /planner_control_interface/std_srvs/automatic_planning '{}' 2>&1 | head -2"
sleep 25

echo "--- [3] TF 链取证(ROS2 侧) ---"
J "source /opt/ros/jazzy/setup.bash 2>/dev/null; timeout 8 ros2 run tf2_ros tf2_echo map odom 2>&1 | grep -E 'Translation|Rotation.*RPY' | head -2"
J "source /opt/ros/jazzy/setup.bash 2>/dev/null; timeout 8 ros2 run tf2_ros tf2_echo odom base_link 2>&1 | grep -E 'Translation|Rotation.*RPY' | head -2"
J "source /opt/ros/jazzy/setup.bash 2>/dev/null; timeout 8 ros2 run tf2_ros tf2_echo base_link lidar3d_frame 2>&1 | grep -E 'Translation|Rotation.*RPY|Invalid|does not exist' | head -2"
echo "--- [3b] TF(ROS1 侧,桥广播) ---"
E "timeout 8 rosrun tf tf_echo world base_link 2>&1 | grep -E 'Translation|RPY' | head -2"
echo "--- [3c] world↔map 恒等验证:同刻 /wm/odom(ROS1,world) vs /slam/odom(ROS2,map) ---"
E "timeout 6 rostopic echo -n1 /wm/odom/pose/pose/position 2>/dev/null | head -3"
J "timeout 6 ros2 topic echo --once /slam/odom nav_msgs/msg/Odometry 2>/dev/null | grep -A3 'position:' | head -4"

echo "--- [4] 体素几何 vs 迷宫地标(等地图积累) ---"
sleep 45
E "timeout 40 python3 /tmp/maze_geo_probe.py /gbplanner_node/tsdf_pointcloud 35"

echo "--- [5] 等 run 结束 ---"
wait $RUN_PID
tail -2 /home/ai4s/worldcheck_run.log
restore_yaml
echo "=== WORLDCHECK END $(date) ==="
} 2>&1 | tee "$OUT"
